"""Adapter model construction and validation on the ``pyfmi_interfaces`` layer.

This module joins a parser-free ``Reduction`` with a :class:`ModelDefinition`.
It owns the adapter model, signal mapping, wire numbering, naming and ordering,
and the artifact identity.  Rendering (JSON, C++, CMake) lives in
:mod:`pyfmi_interop.core.adapter_render`; neither module imports the other
backwards.

Two value namespaces meet here and are deliberately different:

* **FMI value references** are whatever ``pyfmi_interfaces`` assigns: 0-based,
  declaration order, parameters included.  They are never renumbered.
* **Wire field numbers** are ``1..n`` over the FMI input/output signals only,
  in canonical signal-name order.  Parameters are deployment configuration and
  are never wire fields.

The wire-plane model used by the serialization backends is a regular
:class:`~pyfmi_interop.ir.ModelDefinition` whose value references *are* the
wire field numbers.  Its GUID is the same published GUID as the adapter's,
because one artifact has one identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .attributes import (
    DEFAULT_STRING_CAPACITY,
    data_type_from_name,
    direction_from_causality,
)
from .ir import DataType, Direction, ModelDefinition, Signal
from .roles import resolve_role
from .serialization import get as get_serialization

if TYPE_CHECKING:
    from pyfmi_interfaces import Component, ExportIdentity, Reduction

__all__ = [
    "AdapterModel",
    "AdapterSignal",
    "FMI_LAYER",
    "adapter_from_reduction",
    "require_fmi_layer",
    "select_component",
]

#: Published FMI-layer marker written to ``wire.json`` and ``model.json`` and
#: checked by :func:`load_adapter_model`; it is part of the artifact contract.
FMI_LAYER = "psysml2"

def require_fmi_layer():
    """Return the ``pyfmi_interfaces`` FMI-layer emitters the adapter uses.

    The composition layer calls this instead of importing the emitters
    directly, so an installation without ``pyfmi_interfaces`` fails here with
    one clear message rather than inside a render step.
    """

    try:
        from pyfmi_interfaces.c import generate_c_runtime
        from pyfmi_interfaces.c.headers import header_stem, member_expression
        from pyfmi_interfaces.model_description import generate_model_description
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise RuntimeError(
            'the adapter FMI layer requires pyfmi_interfaces: pip install '
            'pyfmi-interfaces'
        ) from error
    return {
        "generate_c_runtime": generate_c_runtime,
        "header_stem": header_stem,
        "member_expression": member_expression,
        "generate_model_description": generate_model_description,
    }


def select_component(
    reduction: Reduction, requested: str | None = None
) -> Component:
    """Select the exported component the adapter carries.

    A name is resolved through :func:`pyfmi_interfaces.core.select_component`,
    the one selection rule, so the caller and the FMI layer cannot disagree.
    Without a name a reduction with one component selects it; several
    components must name one.
    """

    if requested is not None:
        from pyfmi_interfaces.core import select_component as select

        try:
            return select(reduction, requested)
        except ValueError:
            available = ", ".join(
                sorted(candidate.name for candidate in reduction.components)
            )
            raise ValueError(
                f"no exported component named {requested!r}; choose from: {available}"
            ) from None
    components = list(reduction.components)
    if len(components) == 1:
        return components[0]
    available = ", ".join(sorted(candidate.name for candidate in components))
    raise ValueError(
        f"the reduction exports {len(components)} components ({available}); "
        "pass component= to select one"
    )


@dataclass(frozen=True)
class AdapterSignal:
    """One FMI variable and, for a wire signal, its wire field number."""

    name: str
    value_reference: int
    field: int | None
    data_type: DataType
    direction: Direction
    member: str
    capacity: int = 0
    initial: float | int | bool | str | None = None
    unit: str | None = None
    rate_hz: float | None = None

    @property
    def on_wire(self) -> bool:
        return self.direction is not Direction.PARAMETER


@dataclass(frozen=True)
class AdapterModel:
    """The FMI reduction joined with the wire namespace."""

    identifier: str
    model_name: str
    #: Authoritative published FMI GUID, derived from the export identity.
    guid: str
    stem: str
    package: str
    direct: bool
    step_size_s: float | None
    signals: tuple[AdapterSignal, ...]
    role: str
    serialization: str
    #: Wire-plane IR; ``wire_model.guid`` is the same published GUID as ``guid``.
    wire_model: ModelDefinition
    fmi_variables: tuple[AdapterSignal, ...]

    @property
    def parameters(self) -> tuple[AdapterSignal, ...]:
        return tuple(item for item in self.signals if not item.on_wire)

    @property
    def wire_signals(self) -> tuple[AdapterSignal, ...]:
        return tuple(item for item in self.signals if item.on_wire)

    @property
    def contains_parameters(self) -> bool:
        return bool(self.parameters)


def adapter_from_reduction(
    reduction: Reduction,
    model: ModelDefinition,
    *,
    component: str | None = None,
    serialization: str = "protobuf",
    role: str | None = None,
    prefix: str | None = None,
) -> AdapterModel:
    """Join a parser-free ``pyfmi_interfaces`` reduction with ``model``.

    ``model`` supplies the timing, unit and string-capacity metadata that the
    FMI reduction does not carry.  Its signal names must match the reduction
    exactly; a mismatch is an error rather than a silent re-mapping.
    """

    helpers = require_fmi_layer()
    selected = select_component(reduction, component or model.interface)
    identity = reduction.identity
    package = prefix or reduction.package
    stem = helpers["header_stem"](package, selected.name, direct=identity.direct)

    if not _is_identifier(selected.name):
        raise ValueError(
            f"component name {selected.name!r} is not a C identifier; the "
            "psysml2 FMI layer cannot name its build target"
        )

    reduced = {variable.name: variable for variable in selected.variables}
    extra = sorted(set(reduced) - {signal.name for signal in model.signals})
    missing = sorted({signal.name for signal in model.signals} - set(reduced))
    if extra or missing:
        raise ValueError(
            "the IR and the pyfmi_interfaces reduction disagree about the signal "
            f"set (only in SysML: {extra}; only in IR: {missing})"
        )

    wire_names = sorted(
        name
        for name, variable in reduced.items()
        if variable.causality != "parameter"
    )
    fields = {name: index for index, name in enumerate(wire_names, start=1)}

    signals: list[AdapterSignal] = []
    for name, variable in reduced.items():
        source = model.signal(name)
        signals.append(
            AdapterSignal(
                name=name,
                value_reference=variable.value_reference,
                field=fields.get(name),
                data_type=data_type_from_name(variable.type_name),
                direction=direction_from_causality(variable.causality),
                member=helpers["member_expression"](variable.member),
                capacity=(
                    source.capacity
                    if source.data_type is DataType.STRING
                    else 0
                )
                or (
                    DEFAULT_STRING_CAPACITY
                    if variable.type_name == "String"
                    else 0
                ),
                initial=source.initial,
                unit=source.unit,
                rate_hz=source.rate_hz,
            )
        )

    ordered = tuple(sorted(signals, key=lambda item: item.name))
    wire_signals = tuple(item for item in ordered if item.on_wire)
    # One identity per artifact: the wire model carries the published GUID, not
    # a second name-derived GUID, so the fingerprint hashes the same identity.
    published_guid = _guid(identity, selected.name)
    wire_model = ModelDefinition(
        name=selected.name,
        guid=published_guid,
        step_size_s=model.step_size_s,
        signals=tuple(
            Signal(
                name=item.name,
                value_reference=item.field,
                data_type=item.data_type,
                direction=item.direction,
                rate_hz=item.rate_hz,
                unit=item.unit,
                initial=item.initial,
                capacity=item.capacity,
            )
            for item in wire_signals
        ),
        interface=selected.name,
        role=None,
        serialization=serialization,
        realtime=False,
    )
    wire_model.validate()
    resolved_role = resolve_role(wire_model, role)

    return AdapterModel(
        identifier=selected.name,
        model_name=identity.model_name(selected.name),
        guid=published_guid,
        stem=stem,
        package=package,
        direct=identity.direct,
        step_size_s=model.step_size_s,
        signals=ordered,
        role=resolved_role,
        serialization=get_serialization(serialization).name,
        wire_model=wire_model,
        fmi_variables=tuple(
            item for item in ordered if item.direction is not Direction.OUTPUT
        ),
    )


def _guid(identity: ExportIdentity, component: str) -> str:
    from pyfmi_interfaces.core.identity import guid

    return guid(identity.guid_key(component))


def _is_identifier(value: str) -> bool:
    if not value or not (value[0].isascii() and (value[0].isalpha() or value[0] == "_")):
        return False
    return all(char.isascii() and (char.isalnum() or char == "_") for char in value)
