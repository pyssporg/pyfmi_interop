"""Realtime execution IR shared by every generator in :mod:`pyfmi_interop`.

The IR is deliberately independent of SysML and of FMI.  Ingestion maps a
SysML v2 architecture onto it (``sysml.py``), code generation consumes it
(``codegen/``), and packaging serializes it next to the generated binary.  One
IR means every downstream artifact sees the same signals, value references,
rates, and transport bindings.

Design rules carried by this module:

* Value references are assigned exactly once, by :func:`assign_value_references`.
* Timing is stored in seconds, never as a frequency, and is validated before
  generation so a realtime build cannot silently contain an inconsistent plan.
* Every collection is ordered, so two runs over the same input emit
  byte-identical sources.
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
    "Signal",
    "TransportBinding",
    "RateGroup",
    "ModelDefinition",
    "assign_value_references",
    "deterministic_guid",
    "model_from_dict",
    "model_to_dict",
    "REALTIME_GUID_NAMESPACE",
]


#: Namespace used to derive a stable FMU GUID from a model name.  Never change
#: it: existing builds would receive a different GUID.
REALTIME_GUID_NAMESPACE = uuid.UUID("b0f7a4d8-6f36-5c1e-9c2a-4f8b7d3e1a90")


class DataType(str, Enum):
    """FMI scalar types supported by the realtime runtime."""

    REAL = "real"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"


class Direction(str, Enum):
    """Causality of a signal from the point of view of the FMU."""

    INPUT = "input"
    OUTPUT = "output"
    PARAMETER = "parameter"

    @property
    def writable(self) -> bool:
        return self in (Direction.INPUT, Direction.PARAMETER)

    @property
    def readable(self) -> bool:
        return self in (Direction.OUTPUT, Direction.PARAMETER)


@dataclass(frozen=True)
class Signal:
    """One FMI scalar variable plus its realtime execution metadata.

    ``rate_hz`` is the transport/model rate for this signal.  ``None`` means
    "every scheduler step", i.e. the base rate.  String signals have a fixed
    ``capacity`` so the runtime can own their storage and avoid heap traffic in
    the step loop.
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
        if not self.name:
            raise ValueError("signal name must not be empty")
        if self.value_reference < 0:
            raise ValueError(f"{self.name}: value_reference must be >= 0")
        if self.rate_hz is not None and self.rate_hz <= 0:
            raise ValueError(f"{self.name}: rate_hz must be > 0")
        if self.capacity < 0:
            raise ValueError(f"{self.name}: capacity must be >= 0")
        if self.data_type is DataType.STRING and self.capacity == 0:
            raise ValueError(f"{self.name}: string signals require a positive capacity")

    @property
    def period_s(self) -> float | None:
        return None if self.rate_hz is None else 1.0 / self.rate_hz


@dataclass(frozen=True)
class TransportBinding:
    """Binds one signal to one adapter channel.

    ``transport`` is an adapter name registered in :mod:`pyfmi_interop.adapters`.
    ``channel`` is adapter specific: an HLA interaction/attribute name, a DIS
    entity/attribute path, a DCP signal path, a ROS 2 topic, an ED247 stream, etc.
    """

    signal: str
    transport: str
    channel: str
    direction: Direction
    config: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.signal:
            raise ValueError("binding signal must not be empty")
        if not self.transport:
            raise ValueError("binding transport must not be empty")
        if not self.channel:
            raise ValueError("binding channel must not be empty")


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
    bindings: tuple[TransportBinding, ...] = ()
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
        definition can be inspected while it is being assembled.
        """

        names = [signal.name for signal in self.signals]
        if len(names) != len(set(names)):
            duplicates = sorted({name for name in names if names.count(name) > 1})
            raise ValueError(f"duplicate signal names: {', '.join(duplicates)}")

        value_references = [signal.value_reference for signal in self.signals]
        if len(value_references) != len(set(value_references)):
            raise ValueError("duplicate value references")

        known = set(names)
        for binding in self.bindings:
            if binding.signal not in known:
                raise ValueError(
                    f"binding refers to unknown signal: {binding.signal}"
                )

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
    """Assign stable, gap-free value references in canonical signal order."""

    ordered = tuple(sorted(signals, key=lambda item: item.name))
    return tuple(
        replace(signal, value_reference=index)
        for index, signal in enumerate(ordered)
    )


def deterministic_guid(name: str) -> str:
    """Return the stable FMU GUID for ``name``."""

    return str(uuid.uuid5(REALTIME_GUID_NAMESPACE, name))


def model_to_dict(model: ModelDefinition) -> dict[str, Any]:
    """Serialize to a JSON-compatible mapping (deterministic key order)."""

    payload = asdict(model)
    payload["bindings"] = [dict(item) for item in payload["bindings"]]
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
    bindings = tuple(
        TransportBinding(
            signal=item["signal"],
            transport=item["transport"],
            channel=item["channel"],
            direction=Direction(item["direction"]),
            config=dict(item.get("config", {})),
        )
        for item in payload.get("bindings", ())
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
        bindings=bindings,
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


def fingerprint(model: ModelDefinition) -> str:
    """Short stable digest of the IR, recorded in generated build trees."""

    encoded = json.dumps(model_to_dict(model), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
