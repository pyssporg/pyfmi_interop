"""Attribute semantics for the interface the composition layer hands over.

The composition layer reads authored attribute values off its parser-free
reduction and passes plain strings and numbers here.  This module owns the
spelling and precedence rules those values share with the IR: timing keys,
the ``period`` seconds-or-hertz heuristic, the default step, the FMI type and
causality maps, the string capacity, the identifier rule and the signal
projection.  It never receives a parser object or a dialect name.

Timing spells one period in several ways.  On a definition:

``step_size_s`` / ``step_size``
    Seconds.  A model step size, or a signal period when authored on a
    component.
``period_s``
    Seconds.
``period``
    Seconds when the value is <= 1, otherwise Hz (``10`` means 10 Hz).
``rate_hz`` / ``rate``
    Hz.

When several keys are present the order above wins.  A missing model step
size defaults to 1 kHz (0.001 s) and an explicit override wins.  The model
step size is taken from the system, then a component, then a port; a signal
takes its rate from the attributes the composition layer merged for it, so a
port overrides its component.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from . import ir

__all__ = [
    "CAUSALITIES",
    "DEFAULT_STEP_SIZE_S",
    "DEFAULT_STRING_CAPACITY",
    "FMI_TYPES",
    "PERIOD_KEYS",
    "RATE_KEYS",
    "STEP_KEYS",
    "data_type_from_name",
    "direction_from_causality",
    "model_name",
    "period_seconds",
    "period_seconds_from_attributes",
    "rate_hz_from_attributes",
    "sanitize_identifier",
    "signal_from_values",
    "step_size_for_scopes",
    "step_size_from_attributes",
    "string_capacity",
    "unit_from_attributes",
]

#: Scheduler step used when the architecture authors no timing attribute.
DEFAULT_STEP_SIZE_S = 0.001

#: Fixed storage reserved for a string signal's value.
DEFAULT_STRING_CAPACITY = 256

FMI_TYPES = {
    "real": ir.DataType.REAL,
    "integer": ir.DataType.INTEGER,
    "boolean": ir.DataType.BOOLEAN,
    "string": ir.DataType.STRING,
}

CAUSALITIES = {
    "input": ir.Direction.INPUT,
    "output": ir.Direction.OUTPUT,
    "parameter": ir.Direction.PARAMETER,
}

STEP_KEYS = ("step_size_s", "step_size")
PERIOD_KEYS = ("period_s", "period")
RATE_KEYS = ("rate_hz", "rate")


def _first(value: object | None) -> object | None:
    """A list-valued attribute contributes its first element."""

    if isinstance(value, tuple):
        return value[0] if value else None
    return value


def _attribute_value(
    attributes: Mapping[str, object], name: str
) -> object | None:
    return _first(attributes.get(name))


def _as_float(value: object, key: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"timing attribute {key!r} must be a number, got {value!r}")
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"timing attribute {key!r} must be a number, got {value!r}"
        ) from error


def _period_seconds(value: object, key: str) -> float:
    number = _as_float(value, key)
    if key == "period" and number > 1.0:
        number = 1.0 / number
    if number <= 0:
        raise ValueError(f"timing attribute {key!r} must be > 0, got {number!r}")
    return number


def period_seconds(value: object, key: str) -> float:
    """Seconds for one authored timing value under ``key``'s spelling."""

    return _period_seconds(value, key)


def period_seconds_from_attributes(
    attributes: Mapping[str, object],
) -> float | None:
    """The authored period in seconds, or ``None`` when no timing key is set."""

    for key in STEP_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return _period_seconds(value, key)
    for key in PERIOD_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return _period_seconds(value, key)
    for key in RATE_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            rate = _as_float(value, key)
            if rate <= 0:
                raise ValueError(f"timing attribute {key!r} must be > 0, got {rate!r}")
            return 1.0 / rate
    return None


def step_size_from_attributes(
    attributes: Mapping[str, object], explicit: float | None = None
) -> float:
    """Step size from one scope, with the explicit override and default."""

    if explicit is not None:
        step = _as_float(explicit, "step_size_s")
        if step <= 0:
            raise ValueError(f"step_size_s must be > 0, got {step!r}")
        return step
    period = period_seconds_from_attributes(attributes)
    return DEFAULT_STEP_SIZE_S if period is None else period


def step_size_for_scopes(
    system: Mapping[str, object],
    components: Iterable[Mapping[str, object]],
    ports: Iterable[Mapping[str, object]],
    *,
    explicit: float | None = None,
) -> float:
    """The model step: explicit, then system, component, then port scope."""

    if explicit is not None:
        return step_size_from_attributes({}, explicit)
    scopes = [system, *components, *ports]
    for scope in scopes:
        period = period_seconds_from_attributes(scope)
        if period is not None:
            return period
    return DEFAULT_STEP_SIZE_S


def rate_hz_from_attributes(
    attributes: Mapping[str, object],
) -> float | None:
    """Signal rate; an explicit rate key wins over the step/period spelling."""

    for key in RATE_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            rate = _as_float(value, key)
            if rate <= 0:
                raise ValueError(f"timing attribute {key!r} must be > 0, got {rate!r}")
            return rate
    for key in PERIOD_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return 1.0 / _period_seconds(value, key)
    for key in STEP_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return 1.0 / _period_seconds(value, key)
    return None


def unit_from_attributes(attributes: Mapping[str, object]) -> str | None:
    """The authored unit text, or ``None`` when the signal declares none."""

    value = _attribute_value(attributes, "unit")
    return None if value is None else str(value)


def data_type_from_name(type_name: str) -> ir.DataType:
    """The IR data type for an FMI type name, case-insensitively."""

    try:
        return FMI_TYPES[type_name.strip().lower()]
    except KeyError as error:
        raise ValueError(f"unsupported FMI data type {type_name!r}") from error


def direction_from_causality(causality: str) -> ir.Direction:
    """The IR direction for an FMI causality name."""

    try:
        return CAUSALITIES[causality]
    except KeyError as error:
        raise ValueError(f"unsupported FMI causality {causality!r}") from error


def string_capacity(data_type: ir.DataType) -> int:
    """Fixed storage for ``data_type``: one string budget, zero otherwise."""

    return DEFAULT_STRING_CAPACITY if data_type is ir.DataType.STRING else 0


def signal_from_values(
    *,
    name: str,
    type_name: str,
    causality: str,
    value_reference: int | None,
    start: object | None,
    rate_hz: float | None = None,
    unit: str | None = None,
) -> ir.Signal:
    """Project one extracted variable onto an IR signal.

    ``value_reference`` is provisional projection order; zero or ``None``
    means the caller has not numbered it.  A string signal always carries the
    fixed capacity the runtime preallocates.
    """

    data_type = data_type_from_name(type_name)
    return ir.Signal(
        name=name,
        value_reference=value_reference or 1,
        data_type=data_type,
        direction=direction_from_causality(causality),
        rate_hz=rate_hz,
        unit=unit,
        initial=start,
        capacity=string_capacity(data_type),
    )


def sanitize_identifier(text: str) -> str:
    """A C identifier from a package or model name, never empty."""

    cleaned = "".join(
        character if character.isascii() and (character.isalnum() or character == "_")
        else "_"
        for character in text
    )
    if not cleaned:
        return "model"
    if cleaned[0].isdigit():
        return f"_{cleaned}"
    return cleaned


def model_name(
    package: str | None,
    root: str | None,
    explicit: str | None = None,
) -> str:
    """The model name: explicit, then the package, then the root, then a default."""

    if explicit is not None:
        return explicit
    if package:
        return sanitize_identifier(package)
    if root:
        return sanitize_identifier(root)
    return "model"
