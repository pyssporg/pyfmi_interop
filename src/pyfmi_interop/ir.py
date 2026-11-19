"""Realtime execution IR shared by every generator in :mod:`pyfmi_interop`.

The IR is deliberately independent of SysML and of FMI.  Ingestion maps a
SysML v2 architecture onto it (``sysml.py``), code generation consumes it
(``codegen/``), and packaging serializes it next to the generated binary.  One
IR means every downstream artifact sees the same signals, value references,
and rates.

Design rules carried by this module:

* Value references are wire field ids, assigned exactly once by
  :func:`assign_value_references`.  They are **append-only**: a published id is
  never renumbered, reused, or repurposed.  ``0`` is reserved and never a
  legal id; legal ids are ``1..536870911`` excluding protobuf's reserved
  ``19000..19999`` band.
* Timing is stored in seconds, never as a frequency, and is validated before
  generation so a realtime build cannot silently contain an inconsistent plan.
* Every collection is ordered, so two runs over the same input emit
  byte-identical sources.
* :class:`DataType` and :class:`Direction` keep their stable string values for
  JSON while their integer :attr:`~DataType.number` values are frozen for the
  protobuf enums.  ``0`` is "unspecified" on the wire; the numbered members
  start at ``1``.
* String signals are fixed-capacity UTF-8 byte arrays: ``capacity`` is the
  maximum number of encoded bytes, never a character count, and wire values
  must not contain NUL bytes.
* ``unit is None`` means the unit is unspecified (FMI omits it); ``unit == ""``
  means dimensionless.  The two are distinct and round-trip as such.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

__all__ = [
    "DataType",
    "Direction",
    "ProjectionError",
    "Signal",
    "RateGroup",
    "ModelDefinition",
    "assign_value_references",
    "deterministic_guid",
    "encode_string",
    "model_from_dict",
    "model_to_dict",
    "PROTOBUF_MAX_FIELD_NUMBER",
    "PROTOBUF_RESERVED_FIELD_RANGE",
    "REALTIME_GUID_NAMESPACE",
    "STRING_ENCODING",
    "UNASSIGNED_VALUE_REFERENCE",
]


#: Namespace used to derive a stable FMU GUID from a model name.  Never change
#: it: existing builds would receive a different GUID.
REALTIME_GUID_NAMESPACE = uuid.UUID("b0f7a4d8-6f36-5c1e-9c2a-4f8b7d3e1a90")

#: Highest legal protobuf field number.
PROTOBUF_MAX_FIELD_NUMBER = 536_870_911

#: Protobuf reserves this inclusive range for its own implementations.
PROTOBUF_RESERVED_FIELD_RANGE = (19_000, 19_999)

#: ``0`` is reserved and is never a legal wire field id.
UNASSIGNED_VALUE_REFERENCE = 0

#: String signals travel as UTF-8 encoded bytes of at most ``capacity`` bytes.
STRING_ENCODING = "utf-8"


class ProjectionError(ValueError):
    """A signal or model cannot be projected onto the protobuf wire.

    Subclasses :class:`ValueError` so existing callers that only catch
    ``ValueError`` keep working.  ``signal_name`` names the offending signal
    when the failure belongs to one.
    """

    def __init__(self, message: str, *, signal_name: str | None = None) -> None:
        self.signal_name = signal_name
        super().__init__(
            f"signal {signal_name!r}: {message}" if signal_name is not None else message
        )


class DataType(str, Enum):
    """FMI scalar types supported by the realtime runtime.

    The string values are the JSON contract.  The integer :attr:`number` values
    are frozen wire enum numbers; never renumber or reuse one.
    """

    REAL = "real"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"

    @property
    def number(self) -> int:
        """Frozen protobuf enum number (``0`` is wire "unspecified")."""

        return _DATA_TYPE_NUMBERS[self]

    @classmethod
    def from_number(cls, number: int) -> "DataType":
        """Return the member for a frozen wire number."""

        for member, value in _DATA_TYPE_NUMBERS.items():
            if value == number:
                return member
        raise ValueError(f"unknown DataType number: {number}")


class Direction(str, Enum):
    """Causality of a signal from the point of view of the FMU.

    The string values are the JSON contract.  The integer :attr:`number` values
    are frozen wire enum numbers; never renumber or reuse one.
    """

    INPUT = "input"
    OUTPUT = "output"
    PARAMETER = "parameter"

    @property
    def writable(self) -> bool:
        return self in (Direction.INPUT, Direction.PARAMETER)

    @property
    def readable(self) -> bool:
        return self in (Direction.OUTPUT, Direction.PARAMETER)

    @property
    def number(self) -> int:
        """Frozen protobuf enum number (``0`` is wire "unspecified")."""

        return _DIRECTION_NUMBERS[self]

    @classmethod
    def from_number(cls, number: int) -> "Direction":
        """Return the member for a frozen wire number."""

        for member, value in _DIRECTION_NUMBERS.items():
            if value == number:
                return member
        raise ValueError(f"unknown Direction number: {number}")


_DATA_TYPE_NUMBERS = {
    DataType.REAL: 1,
    DataType.INTEGER: 2,
    DataType.BOOLEAN: 3,
    DataType.STRING: 4,
}

_DIRECTION_NUMBERS = {
    Direction.INPUT: 1,
    Direction.OUTPUT: 2,
    Direction.PARAMETER: 3,
}


@dataclass(frozen=True)
class Signal:
    """One FMI scalar variable plus its realtime execution metadata.

    ``rate_hz`` is the transport/model rate for this signal.  ``None`` means
    "every scheduler step", i.e. the base rate.  String signals have a fixed
    ``capacity`` so the runtime can own their storage and avoid heap traffic in
    the step loop; ``capacity`` counts UTF-8 bytes, not characters.

    ``value_reference`` is the wire field id.  ``0`` is reserved and rejected;
    :func:`assign_value_references` assigns ids ``1..n``.

    ``unit is None`` means unspecified; ``unit == ""`` means dimensionless.
    """

    name: str
    value_reference: int
    data_type: DataType
    direction: Direction
    rate_hz: float | None = None
    unit: str | None = None
    initial: float | int | bool | str | None = None
    capacity: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ProjectionError("signal name must not be empty")
        if not isinstance(self.value_reference, int) or isinstance(
            self.value_reference, bool
        ):
            raise ProjectionError(
                "value_reference must be an integer", signal_name=self.name
            )
        if self.value_reference == UNASSIGNED_VALUE_REFERENCE:
            raise ProjectionError(
                "value_reference 0 is reserved; run assign_value_references first",
                signal_name=self.name,
            )
        if self.value_reference < 0:
            raise ProjectionError(
                "value_reference must be > 0", signal_name=self.name
            )
        if self.value_reference > PROTOBUF_MAX_FIELD_NUMBER:
            raise ProjectionError(
                f"value_reference {self.value_reference} exceeds the protobuf "
                f"maximum {PROTOBUF_MAX_FIELD_NUMBER}",
                signal_name=self.name,
            )
        low, high = PROTOBUF_RESERVED_FIELD_RANGE
        if low <= self.value_reference <= high:
            raise ProjectionError(
                f"value_reference {self.value_reference} is in protobuf's "
                f"reserved range {low}..{high}",
                signal_name=self.name,
            )
        if not isinstance(self.data_type, DataType):
            raise ProjectionError(
                "data_type must be a DataType", signal_name=self.name
            )
        if not isinstance(self.direction, Direction):
            raise ProjectionError(
                "direction must be a Direction", signal_name=self.name
            )
        if self.rate_hz is not None and self.rate_hz <= 0:
            raise ProjectionError("rate_hz must be > 0", signal_name=self.name)
        if not isinstance(self.capacity, int) or isinstance(self.capacity, bool):
            raise ProjectionError(
                "capacity must be an integer", signal_name=self.name
            )
        if self.capacity < 0:
            raise ProjectionError("capacity must be >= 0", signal_name=self.name)
        if self.data_type is DataType.STRING and self.capacity == 0:
            raise ProjectionError(
                "string signals require a positive capacity",
                signal_name=self.name,
            )
        if self.unit is not None:
            if not isinstance(self.unit, str):
                raise ProjectionError(
                    "unit must be a string or None", signal_name=self.name
                )
            if "\x00" in self.unit:
                raise ProjectionError(
                    "unit must not contain NUL", signal_name=self.name
                )
        self._validate_initial()

    def _validate_initial(self) -> None:
        if self.initial is None:
            return
        if self.data_type is DataType.REAL:
            if isinstance(self.initial, bool) or not isinstance(
                self.initial, (int, float)
            ):
                raise ProjectionError(
                    "real initial value must be an int or float",
                    signal_name=self.name,
                )
        elif self.data_type is DataType.INTEGER:
            if isinstance(self.initial, bool) or not isinstance(self.initial, int):
                raise ProjectionError(
                    "integer initial value must be an int", signal_name=self.name
                )
        elif self.data_type is DataType.BOOLEAN:
            if not isinstance(self.initial, bool):
                raise ProjectionError(
                    "boolean initial value must be a bool", signal_name=self.name
                )
        elif self.data_type is DataType.STRING:
            if not isinstance(self.initial, str):
                raise ProjectionError(
                    "string initial value must be a str", signal_name=self.name
                )
            if self.capacity == 0:
                raise ProjectionError(
                    "string signals require a positive capacity",
                    signal_name=self.name,
                )
            encode_string(self.initial, self.capacity, signal_name=self.name)

    def check_projection(self) -> None:
        """Raise :class:`ProjectionError` if this signal cannot be a wire field."""

        if not _is_proto_field_name(self.name):
            raise ProjectionError(
                "name is not a legal protobuf field identifier "
                "(letters, digits, underscore; not starting with a digit)",
                signal_name=self.name,
            )

    @property
    def period_s(self) -> float | None:
        return None if self.rate_hz is None else 1.0 / self.rate_hz

    @property
    def wire_capacity(self) -> int:
        """Maximum wire byte length for a string signal, ``0`` for other types."""

        return self.capacity if self.data_type is DataType.STRING else 0

    @property
    def initial_bytes(self) -> bytes | None:
        """The initial string as wire bytes, or ``None`` for non-string signals."""

        if self.data_type is not DataType.STRING or self.initial is None:
            return None
        return encode_string(self.initial, self.capacity, signal_name=self.name)


@dataclass(frozen=True)
class RateGroup:
    """A set of signals stepped at ``period_s`` with a ``deadline_s`` budget."""

    name: str
    period_s: float
    deadline_s: float
    signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.period_s <= 0:
            raise ValueError(f"{self.name}: period_s must be > 0")
        if self.deadline_s <= 0:
            raise ValueError(f"{self.name}: deadline_s must be > 0")
        if self.deadline_s > self.period_s:
            raise ValueError(f"{self.name}: deadline_s must not exceed period_s")


@dataclass(frozen=True)
class ModelDefinition:
    """Everything the generator needs to emit one realtime model runtime."""

    name: str
    guid: str
    step_size_s: float
    realtime: bool = True
    signals: tuple[Signal, ...] = ()
    rate_groups: tuple[RateGroup, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("model name must not be empty")
        if not _is_identifier(self.name):
            raise ValueError(
                f"model name {self.name!r} must be a C identifier "
                "(letters, digits, underscore; not starting with a digit)"
            )
        if self.step_size_s <= 0:
            raise ValueError("step_size_s must be > 0")
        if not self.guid:
            raise ValueError("guid must not be empty")

    @property
    def base_period_s(self) -> float:
        return self.step_size_s

    def signal(self, name: str) -> Signal:
        for item in self.signals:
            if item.name == name:
                return item
        raise KeyError(f"unknown signal: {name}")

    def validate(self) -> None:
        """Raise :class:`ValueError` if the definition is not executable.

        Called by the generator, not by the constructor, so a partially built
        definition can be inspected while it is being assembled.  Signals that
        cannot be projected onto the protobuf wire raise :class:`ProjectionError`.
        """

        names = [signal.name for signal in self.signals]
        if len(names) != len(set(names)):
            duplicates = sorted({name for name in names if names.count(name) > 1})
            raise ValueError(f"duplicate signal names: {', '.join(duplicates)}")

        seen_ids: dict[int, str] = {}
        for signal in self.signals:
            signal.check_projection()
            previous = seen_ids.get(signal.value_reference)
            if previous is not None:
                raise ProjectionError(
                    f"duplicate value reference {signal.value_reference} "
                    f"(also used by {previous!r})",
                    signal_name=signal.name,
                )
            seen_ids[signal.value_reference] = signal.name

        known = set(names)
        grouped: set[str] = set()
        for group in self.rate_groups:
            if group.period_s < self.step_size_s - 1e-12:
                raise ValueError(
                    f"{group.name}: period {group.period_s}s is shorter than the "
                    f"step size {self.step_size_s}s"
                )
            ratio = group.period_s / self.step_size_s
            if abs(ratio - round(ratio)) > 1e-9:
                raise ValueError(
                    f"{group.name}: period {group.period_s}s is not an integer "
                    f"multiple of step size {self.step_size_s}s"
                )
            for signal_name in group.signals:
                if signal_name not in known:
                    raise ValueError(
                        f"{group.name}: unknown signal in rate group: {signal_name}"
                    )
                if signal_name in grouped:
                    raise ValueError(
                        f"signal {signal_name} belongs to more than one rate group"
                    )
                grouped.add(signal_name)

        for signal in self.signals:
            if signal.rate_hz is not None:
                period = signal.period_s
                assert period is not None
                ratio = period / self.step_size_s
                if abs(ratio - round(ratio)) > 1e-9:
                    raise ValueError(
                        f"{signal.name}: rate {signal.rate_hz} Hz does not align "
                        f"with step size {self.step_size_s}s"
                    )

    def with_value_references(self) -> "ModelDefinition":
        return replace(self, signals=assign_value_references(self.signals))


def assign_value_references(signals: Iterable[Signal]) -> tuple[Signal, ...]:
    """Assign gap-free wire field ids ``1..n`` in canonical signal order.

    Call this once per model, before publishing it.  Field ids are append-only:
    once a model version has shipped, never renumber or reuse its ids; add a
    new schema version instead.
    """

    ordered = tuple(sorted(signals, key=lambda item: item.name))
    if len(ordered) > PROTOBUF_MAX_FIELD_NUMBER:
        raise ProjectionError(
            f"{len(ordered)} signals exceed the protobuf field-number space"
        )
    return tuple(
        replace(signal, value_reference=index)
        for index, signal in enumerate(ordered, start=1)
    )


def deterministic_guid(name: str) -> str:
    """Return the stable FMU GUID for ``name``."""

    return str(uuid.uuid5(REALTIME_GUID_NAMESPACE, name))


def encode_string(value: str, capacity: int, *, signal_name: str | None = None) -> bytes:
    """Encode a wire string as UTF-8 bytes bounded by ``capacity``.

    The result is at most ``capacity`` bytes and contains no NUL bytes.  The
    capacity is a byte budget, so a multi-byte character consumes more than one
    byte.  Raises :class:`ProjectionError` when the value cannot be represented.
    """

    if not isinstance(value, str):
        raise ProjectionError("string value must be a str", signal_name=signal_name)
    if capacity <= 0:
        raise ProjectionError(
            "string values require a positive capacity", signal_name=signal_name
        )
    if "\x00" in value:
        raise ProjectionError("string values must not contain NUL", signal_name=signal_name)
    encoded = value.encode(STRING_ENCODING)
    if len(encoded) > capacity:
        raise ProjectionError(
            f"string value is {len(encoded)} {STRING_ENCODING} bytes, "
            f"exceeding capacity {capacity}",
            signal_name=signal_name,
        )
    return encoded


def model_to_dict(model: ModelDefinition) -> dict[str, Any]:
    """Serialize to a JSON-compatible mapping (deterministic key order)."""

    payload = asdict(model)
    payload["metadata"] = dict(payload["metadata"])
    return payload


def model_from_dict(payload: Mapping[str, Any]) -> ModelDefinition:
    """Inverse of :func:`model_to_dict`."""

    signals = tuple(
        Signal(
            name=item["name"],
            value_reference=int(item["value_reference"]),
            data_type=DataType(item["data_type"]),
            direction=Direction(item["direction"]),
            rate_hz=item.get("rate_hz"),
            unit=item.get("unit"),
            initial=item.get("initial"),
            capacity=int(item.get("capacity", 0)),
        )
        for item in payload.get("signals", ())
    )
    rate_groups = tuple(
        RateGroup(
            name=item["name"],
            period_s=float(item["period_s"]),
            deadline_s=float(item["deadline_s"]),
            signals=tuple(item.get("signals", ())),
        )
        for item in payload.get("rate_groups", ())
    )
    return ModelDefinition(
        name=payload["name"],
        guid=payload["guid"],
        step_size_s=float(payload["step_size_s"]),
        realtime=bool(payload.get("realtime", True)),
        signals=signals,
        rate_groups=rate_groups,
        metadata=dict(payload.get("metadata", {})),
        description=payload.get("description", ""),
    )


def write_model_json(model: ModelDefinition, path: Any) -> None:
    """Write the IR as canonical JSON (stable order, trailing newline)."""

    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(model_to_dict(model), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _is_identifier(value: str) -> bool:
    if not value:
        return False
    first = value[0]
    if not (first.isascii() and (first.isalpha() or first == "_")):
        return False
    return all(char.isascii() and (char.isalnum() or char == "_") for char in value)


def _is_proto_field_name(value: str) -> bool:
    """A protobuf field identifier without C++-reserved double underscores."""

    return _is_identifier(value) and "__" not in value


def fingerprint(model: ModelDefinition) -> str:
    """Short stable digest of the IR, recorded in generated build trees."""

    encoded = json.dumps(model_to_dict(model), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
