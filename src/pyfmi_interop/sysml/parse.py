"""Ingestion of a SysML v2 architecture into the public model specification.

The SysML dialect itself is owned by :mod:`pycps_sysml2`; the FMI variable
reduction is owned by :mod:`pyfmi_sysml2.core`.  This module only maps that
reduction onto :mod:`pyfmi_interop.core`, so parsing is never re-implemented
here.  Both packages are optional dependencies: importing this module works
without them, calling :func:`parse` or the compatibility helpers raises a
:class:`RuntimeError` naming the ``sysml`` extra when they are missing.

A SysML source is parsed exactly once.  :func:`parse` returns a
:class:`ParsedModel` holding both the projected specification and the opaque
``pycps_sysml2`` architecture; :func:`pyfmi_interop.sysml.generate_adapter`
consumes that handle and never reloads the source.

Timing attributes are read defensively from part and port definitions:

``step_size_s`` / ``step_size``
    Seconds per scheduler step.  The model step size, or a signal period when
    authored on a component.
``period_s``
    Seconds.
``period``
    Seconds when the value is <= 1, otherwise Hz (``10`` means 10 Hz).
``rate_hz`` / ``rate``
    Hz.

When several keys are present the order above wins.  A missing model step size
defaults to 1 kHz (0.001 s) and is overridden by ``step_size_s=``.  The model
step size is taken from the system, then a component, then a port; a signal
takes its rate from the merged component/port attributes, so a port overrides
its component.

Timing and transport metadata are ordinary typed attributes.  On a port
definition the attribute must be typed by a dialect container marker (for
example an ``attribute def`` specializing ``ParameterSet``) so the FMI
reduction skips it instead of turning it into a signal field.  On a part
definition any resolved ``attribute def`` is enough; a flat untyped attribute
is rejected by the parameter dialect.

Transport attributes are not interpreted: the repository carries bytes, not
protocol bindings, so ``transport``, ``channel``, and ``transport_endpoint``
remain author metadata only.

String signals get ``DEFAULT_STRING_CAPACITY`` bytes so the runtime owns their
storage and never allocates inside the step loop.  ``pyfmi_sysml2.Variable``
carries neither a unit nor an explicit "absent" marker for the initial value,
so a signal without a ``unit`` attribute gets ``unit=None`` and ``initial`` is
exactly the variable's authored ``start`` (or ``None``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core import ModelSpec, ir
from ..core.ir import deterministic_guid
from .adapter import _select_component
from .definitions import load_with_interop

__all__ = [
    "DEFAULT_STEP_SIZE_S",
    "DEFAULT_STRING_CAPACITY",
    "ParsedModel",
    "load_architecture",
    "load_model",
    "model_from_architecture",
    "parse",
]

#: Scheduler step used when the architecture authors no timing attribute.
DEFAULT_STEP_SIZE_S = 0.001

#: Fixed storage reserved for a string signal's value.
DEFAULT_STRING_CAPACITY = 256

_SYSML_EXTRA = 'the "sysml" extra: pip install "pyfmi-interop[sysml]"'

_FMI_TYPES = {
    "real": ir.DataType.REAL,
    "integer": ir.DataType.INTEGER,
    "boolean": ir.DataType.BOOLEAN,
    "string": ir.DataType.STRING,
}

_CAUSALITIES = {
    "input": ir.Direction.INPUT,
    "output": ir.Direction.OUTPUT,
    "parameter": ir.Direction.PARAMETER,
}

_STEP_KEYS = ("step_size_s", "step_size")
_PERIOD_KEYS = ("period_s", "period")
_RATE_KEYS = ("rate_hz", "rate")


@dataclass(frozen=True)
class ParsedModel:
    """One SysML parse: the projected specification and the source handle."""

    spec: ModelSpec
    architecture: object  # opaque pycps_sysml2 handle
    unit: str  # selected exported component name
    composition: str | None  # resolved composition root, if any


def parse(
    source: str | Path,
    *,
    includes: Iterable[str | Path] = (),
    component: str | None = None,
    composition: str | None = None,
    name: str | None = None,
    step_size_s: float | None = None,
    realtime: bool = True,
) -> ParsedModel:
    """Parse ``source`` once and return the specification plus its handle."""

    architecture = load_architecture(source, includes=includes)
    system, _, unit = _resolve_selection(
        architecture, composition=composition, component=component
    )
    spec = _project_spec(
        architecture,
        system,
        [unit],
        name=name,
        step_size_s=step_size_s,
        realtime=realtime,
    )
    return ParsedModel(
        spec=spec,
        architecture=architecture,
        unit=unit.name,
        composition=composition,
    )


def load_architecture(
    source: str | Path,
    *,
    includes: Iterable[str | Path] = (),
) -> Any:
    """Load a SysML v2 file or directory into an ``Architecture``.

    ``includes`` are extra package roots (files or directories) merged into the
    load, so a model can import a library that defines its FMU base or the
    exported leaf itself.  The bundled ``PyfmiInterop`` library is added to the
    roots only when the architecture imports it, exactly as in
    :func:`load_model`.  Call this once to export several units from the same
    parse, passing each name to :func:`model_from_architecture` as
    ``composition=``.
    """

    pycps_sysml2, _, _ = _require_sysml()
    return load_with_interop(source, pycps_sysml2.load, includes=includes)


def load_model(
    source: str | Path,
    **kwargs: Any,
) -> ModelSpec:
    """Parse ``source`` and return its public specification."""

    return parse(source, **kwargs).spec


def model_from_architecture(
    architecture: Any,
    *,
    name: str | None = None,
    step_size_s: float | None = None,
    realtime: bool = True,
    composition: str | None = None,
) -> ModelSpec:
    """Reduce an already loaded architecture onto the public specification.

    ``composition`` selects the part definition whose components are exported;
    without it the reduction picks the single ``:> FmuModel`` leaf, or asks for
    a name when several leaves exist.  The model name defaults to the
    architecture's package name, sanitized to a C identifier.  Passing ``name``
    keeps it verbatim so an invalid name is rejected by
    :class:`~pyfmi_interop.ir.ModelDefinition` instead of being silently
    rewritten.
    """

    _, components, resolve_system = _require_sysml()

    system = _system_definition(architecture, resolve_system, composition)
    selected = components(architecture, composition=composition)
    return _project_spec(
        architecture,
        system,
        selected,
        name=name,
        step_size_s=step_size_s,
        realtime=realtime,
    )


# -- selection -------------------------------------------------------------


def _resolve_selection(
    architecture: Any,
    *,
    composition: str | None,
    component: str | None,
) -> tuple[Any | None, list[Any], Any]:
    """Resolve the composition root and select the exported unit once."""

    _, components, resolve_system = _require_sysml()
    system = _system_definition(architecture, resolve_system, composition)
    selected = components(architecture, composition=composition)
    unit = _select_component(selected, component)
    return system, selected, unit


# -- lazy dependencies -----------------------------------------------------


def _require_sysml():
    try:
        import pycps_sysml2
        from pyfmi_sysml2.core import components, resolve_system
    except ImportError as error:
        raise RuntimeError(f"SysML ingestion requires {_SYSML_EXTRA}") from error
    return pycps_sysml2, components, resolve_system


# -- architecture lookups --------------------------------------------------


def _model_name(architecture: Any, name: str | None, system: Any | None) -> str:
    if name is not None:
        return name
    package_name = getattr(architecture, "package_name", None)
    if package_name:
        return _identifier(package_name)
    if system is not None:
        return _identifier(system.name)
    return "model"


def _system_definition(
    architecture: Any, resolve_system, composition: str | None
) -> Any | None:
    try:
        return resolve_system(architecture, composition)
    except (KeyError, ValueError):
        return None


def _part_definition(architecture: Any, name: str) -> Any | None:
    for definition in getattr(architecture, "part_definitions", {}).values():
        if definition.name == name:
            return definition
    return None


def _port_attributes(architecture: Any, component: Any) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    resolve_port = getattr(architecture, "resolve_port", None)
    if resolve_port is None:
        return result
    for group in component.ports:
        definition = resolve_port(group.definition)
        if definition is not None and definition.attributes:
            result[group.name] = dict(definition.attributes)
    return result


def _attributes(definition: Any | None) -> Mapping[str, object]:
    if definition is None:
        return {}
    return getattr(definition, "attributes", {}) or {}


def _variable_attributes(
    variable: Any,
    component_attributes: Mapping[str, object],
    port_attributes: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object]:
    for port_name, attributes in port_attributes.items():
        if variable.name == port_name or variable.name.startswith(f"{port_name}."):
            return {**component_attributes, **attributes}
    return component_attributes


# -- attribute normalization ----------------------------------------------


def _attribute_value(attributes: Mapping[str, object], name: str) -> object | None:
    """Raw value of ``name``; list-valued attributes keep their first element."""

    raw = attributes.get(name)
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    if isinstance(value, tuple):
        return value[0] if value else None
    return value


def _text_attribute(attributes: Mapping[str, object], name: str) -> str | None:
    value = _attribute_value(attributes, name)
    return None if value is None else str(value)


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


def _period_seconds_from_attributes(attributes: Mapping[str, object]) -> float | None:
    for key in _STEP_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return _period_seconds(value, key)
    for key in _PERIOD_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return _period_seconds(value, key)
    for key in _RATE_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            rate = _as_float(value, key)
            if rate <= 0:
                raise ValueError(f"timing attribute {key!r} must be > 0, got {rate!r}")
            return 1.0 / rate
    return None


def _step_size_from_attributes(
    attributes: Mapping[str, object], explicit: float | None
) -> float:
    if explicit is not None:
        step = _as_float(explicit, "step_size_s")
        if step <= 0:
            raise ValueError(f"step_size_s must be > 0, got {step!r}")
        return step
    period = _period_seconds_from_attributes(attributes)
    return DEFAULT_STEP_SIZE_S if period is None else period


def _model_step_size(
    architecture: Any,
    components: list[Any],
    system_attributes: Mapping[str, object],
    explicit: float | None,
) -> float:
    """First authored step period in system, component, then port scope."""

    if explicit is not None:
        return _step_size_from_attributes({}, explicit)
    scopes: list[Mapping[str, object]] = [system_attributes]
    for component in components:
        scopes.append(_attributes(_part_definition(architecture, component.name)))
        scopes.extend(_port_attributes(architecture, component).values())
    for scope in scopes:
        period = _period_seconds_from_attributes(scope)
        if period is not None:
            return period
    return DEFAULT_STEP_SIZE_S


def _rate_hz_from_attributes(attributes: Mapping[str, object]) -> float | None:
    """Signal rate; explicit rate keys win over the step/period spelling."""

    for key in _RATE_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            rate = _as_float(value, key)
            if rate <= 0:
                raise ValueError(f"timing attribute {key!r} must be > 0, got {rate!r}")
            return rate
    for key in _PERIOD_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return 1.0 / _period_seconds(value, key)
    for key in _STEP_KEYS:
        value = _attribute_value(attributes, key)
        if value is not None:
            return 1.0 / _period_seconds(value, key)
    return None


# -- variable mapping ------------------------------------------------------


def _data_type(type_name: str) -> ir.DataType:
    try:
        return _FMI_TYPES[type_name.strip().lower()]
    except KeyError as error:
        raise ValueError(f"unsupported FMI data type {type_name!r}") from error


def _direction(causality: str) -> ir.Direction:
    try:
        return _CAUSALITIES[causality]
    except KeyError as error:
        raise ValueError(f"unsupported FMI causality {causality!r}") from error


def _signal_from_variable(
    variable: Any,
    *,
    rate_hz: float | None,
    unit: str | None,
) -> ir.Signal:
    data_type = _data_type(variable.type_name)
    return ir.Signal(
        name=variable.name,
        value_reference=variable.value_reference or 1,
        data_type=data_type,
        direction=_direction(variable.causality),
        rate_hz=rate_hz,
        unit=unit,
        initial=getattr(variable, "start", None),
        capacity=DEFAULT_STRING_CAPACITY if data_type is ir.DataType.STRING else 0,
    )


def _identifier(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", text)
    if not cleaned:
        return "model"
    if cleaned[0].isdigit():
        return f"_{cleaned}"
    return cleaned


def _project_spec(
    architecture: Any,
    system: Any | None,
    selected: list[Any],
    *,
    name: str | None,
    step_size_s: float | None,
    realtime: bool,
) -> ModelSpec:
    """Project the selected components onto one public specification."""

    model_name = _model_name(architecture, name, system)
    system_attributes = _attributes(system)
    step_size = _model_step_size(
        architecture, selected, system_attributes, step_size_s
    )

    signals: list[ir.Signal] = []
    for component in selected:
        part = _part_definition(architecture, component.name)
        component_attributes = _attributes(part)
        port_attributes = _port_attributes(architecture, component)

        for variable in component.variables:
            attributes = _variable_attributes(
                variable, component_attributes, port_attributes
            )
            rate_hz = _rate_hz_from_attributes(attributes)
            signals.append(
                _signal_from_variable(
                    variable,
                    rate_hz=rate_hz,
                    unit=_text_attribute(attributes, "unit"),
                )
            )

    # The payload message is named after the part definition whose interface
    # the model carries.  A container that combines several exported components
    # has no single part definition, so the message falls back to the model name.
    interface = selected[0].name if len(selected) == 1 else None
    return ModelSpec(
        name=model_name,
        guid=deterministic_guid(model_name),
        step_size_s=step_size,
        realtime=realtime,
        signals=ir.assign_value_references(signals),
        interface=interface,
    )
