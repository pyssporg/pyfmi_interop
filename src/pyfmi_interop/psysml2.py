"""Adapter generation on the ``pyfmi_sysml2`` FMI layer.

This module is the opt-in replacement for the FMI facade the repository used to
maintain itself (``runtime/src/fmi2_cs_api.cpp``).  ``pyfmi_sysml2`` emits the
FMI 2.0 C interface, the C headers, the bundled FMI headers and
``modelDescription.xml``; this module supplies the five model hooks and keeps
the wire plane (:mod:`pyfmi_interop.wire`, the serialization backends,
``wire.json``, ``.proto``).

Two value namespaces meet here and are deliberately different:

* **FMI value references** are whatever ``pyfmi_sysml2`` assigns: 0-based,
  declaration order, parameters included.  They are never renumbered.
* **Wire field numbers** are ``1..n`` over the FMI input/output signals only,
  in canonical signal-name order.  Parameters are deployment configuration and
  are never wire fields.

``wire.json`` carries both per signal (``value_reference`` and ``field``), the
schemas use wire field numbers only, and the model id is derived from the wire
field number plus data type so that adding, removing or retyping a parameter
never moves it.

The wire-plane model used by the serialization backends is a regular
:class:`~pyfmi_interop.ir.ModelDefinition` whose value references *are* the
wire field numbers.  The FMI side is carried by the ``pyfmi_sysml2``
``Component`` reduction and recorded in ``model.json``.  A JSON ``model.json``
input has no SysML architecture behind it, so it cannot use this layer; the
legacy facade is its path until that input is retired.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ir import DataType, Direction, ModelDefinition, Signal, fingerprint
from .roles import resolve_role
from .serialization import get as get_serialization
from .serialization.naming import message_identifier, wire_direction
from .serialization.protobuf import render_proto
from .wire import model_id

__all__ = [
    "AdapterModel",
    "AdapterSignal",
    "adapter_from_architecture",
    "adapter_model_json",
    "generate_adapter_model",
    "load_adapter_model",
    "render_adapter_wire_json",
    "wire_model_from_adapter_json",
]

_FMI_LAYER = "psysml2"
_DEFAULT_STRING_CAPACITY = 256

_CAUSALITY = {
    "input": Direction.INPUT,
    "output": Direction.OUTPUT,
    "parameter": Direction.PARAMETER,
}

_DATA_TYPE = {
    "Real": DataType.REAL,
    "Integer": DataType.INTEGER,
    "Boolean": DataType.BOOLEAN,
    "String": DataType.STRING,
}


def _require_pyfmi_sysml2():
    try:
        import pyfmi_sysml2
        from pyfmi_sysml2.c import generate_c_runtime
        from pyfmi_sysml2.c.headers import header_stem, member_expression
        from pyfmi_sysml2.core import (
            architecture,
            components,
            export_identity,
            resolve_system,
        )
        from pyfmi_sysml2.model_description import generate_model_description
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise RuntimeError(
            'the "psysml2" FMI layer requires pyfmi_sysml2: pip install '
            '"pyfmi-interop[sysml]"'
        ) from error
    return {
        "pyfmi_sysml2": pyfmi_sysml2,
        "generate_c_runtime": generate_c_runtime,
        "header_stem": header_stem,
        "member_expression": member_expression,
        "architecture": architecture,
        "components": components,
        "export_identity": export_identity,
        "resolve_system": resolve_system,
        "generate_model_description": generate_model_description,
    }


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
    guid: str
    stem: str
    package: str
    direct: bool
    step_size_s: float | None
    signals: tuple[AdapterSignal, ...]
    role: str
    serialization: str
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


def adapter_from_architecture(
    architecture: Any,
    model: ModelDefinition,
    *,
    component: str | None = None,
    composition: str | None = None,
    serialization: str = "protobuf",
    role: str | None = None,
    prefix: str | None = None,
) -> AdapterModel:
    """Join the ``pyfmi_sysml2`` reduction of ``architecture`` with ``model``.

    ``model`` supplies the timing, unit and string-capacity metadata that the
    FMI reduction does not carry.  Its signal names must match the reduction
    exactly; a mismatch is an error rather than a silent re-mapping.
    """

    helpers = _require_pyfmi_sysml2()
    system = helpers["resolve_system"](architecture, composition)
    exported = helpers["components"](architecture, composition=composition)
    selected = _select_component(exported, component or model.interface)
    identity = helpers["export_identity"](architecture, system)
    package = prefix or architecture.package_name
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
            "the IR and the pyfmi_sysml2 reduction disagree about the signal "
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
                data_type=_DATA_TYPE[variable.type_name],
                direction=_CAUSALITY[variable.causality],
                member=helpers["member_expression"](variable.member),
                capacity=(
                    source.capacity
                    if source.data_type is DataType.STRING
                    else 0
                )
                or (
                    _DEFAULT_STRING_CAPACITY
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
    wire_model = ModelDefinition(
        name=selected.name,
        guid=model.guid,
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
        guid=_guid(helpers, identity, selected.name),
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


def _select_component(components: list[Any], requested: str | None) -> Any:
    if requested is not None:
        for candidate in components:
            if candidate.name == requested:
                return candidate
        available = ", ".join(sorted(item.name for item in components))
        raise ValueError(
            f"no exported component named {requested!r}; choose from: {available}"
        )
    if len(components) == 1:
        return components[0]
    available = ", ".join(sorted(item.name for item in components))
    raise ValueError(
        f"the architecture exports {len(components)} components ({available}); "
        "pass component= to select one"
    )


def _guid(helpers: dict[str, Any], identity: Any, component: str) -> str:
    from pyfmi_sysml2.core.identity import guid

    return guid(identity.guid_key(component))


def _is_identifier(value: str) -> bool:
    if not value or not (value[0].isascii() and (value[0].isalpha() or value[0] == "_")):
        return False
    return all(char.isascii() and (char.isalnum() or char == "_") for char in value)


def _stable_float(value: float) -> float:
    number = float(value)
    return 0.0 if number == 0.0 else number


def render_adapter_wire_json(adapter: AdapterModel) -> str:
    """Return ``wire.json`` with both value namespaces per signal."""

    backend = get_serialization(adapter.serialization)
    payload = {
        "fmi_layer": _FMI_LAYER,
        "format": backend.name,
        "format_id": backend.format_id,
        "format_version": 1,
        "guid": adapter.guid,
        "interface": adapter.wire_model.interface,
        "model": adapter.wire_model.name,
        "model_id": model_id(adapter.wire_model).hex(),
        "payload_message": message_identifier(
            adapter.wire_model.interface or adapter.wire_model.name
        ),
        "proto_package": (
            "pyfmi_interop.wire" if backend.name == "protobuf" else None
        ),
        "role": adapter.role,
        "parameters": [
            {
                "name": item.name,
                "value_reference": item.value_reference,
                "data_type": item.data_type.value,
                "direction": item.direction.value,
                "initial": item.initial,
            }
            for item in adapter.parameters
        ],
        "signals": [
            {
                "field": item.field,
                "value_reference": item.value_reference,
                "name": item.name,
                "wire": wire_direction(item),
                "data_type": item.data_type.value,
                "direction": item.direction.value,
                "rate_hz": (
                    None if item.rate_hz is None else _stable_float(item.rate_hz)
                ),
                "unit": item.unit,
                "capacity": item.capacity,
            }
            for item in adapter.wire_signals
        ],
    }
    if adapter.step_size_s is not None:
        # Kept for the sibling consumer that still reads this key; it is not a
        # wire fact and never contributes to ``model_id``.
        payload["step_size_s"] = _stable_float(adapter.step_size_s)
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def adapter_model_json(adapter: AdapterModel) -> bytes:
    """Return the deterministic ``model.json`` for the joined model."""

    payload = {
        "fmi_layer": _FMI_LAYER,
        "name": adapter.identifier,
        "identifier": adapter.identifier,
        "model_name": adapter.model_name,
        "guid": adapter.guid,
        "interface": adapter.wire_model.interface,
        "fingerprint": fingerprint(adapter.wire_model),
        "role": adapter.role,
        "serialization": adapter.serialization,
        "signals": [
            {
                "name": item.name,
                "value_reference": item.value_reference,
                "field": item.field,
                "data_type": item.data_type.value,
                "direction": item.direction.value,
                "member": item.member,
                "capacity": item.capacity,
                "initial": item.initial,
                "unit": item.unit,
                "rate_hz": item.rate_hz,
            }
            for item in adapter.signals
        ],
    }
    if adapter.step_size_s is not None:
        payload["step_size_s"] = _stable_float(adapter.step_size_s)
    return (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def load_adapter_model(model_dir: str | Path) -> dict[str, Any]:
    """Read the ``model.json`` this layer wrote, without the IR round-trip."""

    payload = json.loads(
        (Path(model_dir) / "model.json").read_text(encoding="utf-8")
    )
    if payload.get("fmi_layer") != _FMI_LAYER:
        raise ValueError(
            f"{model_dir}: model.json was not written by the {_FMI_LAYER} FMI layer"
        )
    return payload


def wire_model_from_adapter_json(payload: Any) -> ModelDefinition:
    """Rebuild the wire-plane IR (value reference == wire field) for packaging."""

    signals = tuple(
        Signal(
            name=item["name"],
            value_reference=int(item["field"]),
            data_type=DataType(item["data_type"]),
            direction=Direction(item["direction"]),
            rate_hz=item.get("rate_hz"),
            unit=item.get("unit"),
            initial=item.get("initial"),
            capacity=int(item.get("capacity", 0)),
        )
        for item in payload["signals"]
        if item.get("field") is not None
    )
    return ModelDefinition(
        name=payload["name"],
        guid=payload["guid"],
        step_size_s=(
            None
            if payload.get("step_size_s") is None
            else float(payload["step_size_s"])
        ),
        realtime=False,
        signals=signals,
        interface=payload.get("interface"),
        role=payload.get("role"),
        serialization=payload.get("serialization"),
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


_DEFAULT_EXPERIMENT = re.compile(
    r"\n[ \t]*<DefaultExperiment\b[^>]*(?:/>|>.*?</DefaultExperiment>)",
    re.DOTALL,
)


def _strip_default_experiment(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    stripped = _DEFAULT_EXPERIMENT.sub("", text)
    if stripped != text:
        _write(path, stripped)


def generate_adapter_model(
    model: ModelDefinition,
    out_dir: str | Path,
    *,
    source: Any,
    serialization: str = "protobuf",
    role: str | None = None,
    composition: str | None = None,
    component: str | None = None,
    prefix: str | None = None,
) -> Path:
    """Write the adapter source tree with ``pyfmi_sysml2`` as the FMI layer."""

    helpers = _require_pyfmi_sysml2()
    if source is None:
        raise ValueError(
            'fmi_layer="psysml2" needs source= (a SysML path or Architecture); '
            "a JSON model.json input has no SysML architecture behind it"
        )
    architecture = helpers["architecture"](source)
    adapter = adapter_from_architecture(
        architecture,
        model,
        component=component,
        composition=composition,
        serialization=serialization,
        role=role,
        prefix=prefix,
    )

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    helpers["generate_c_runtime"](
        architecture,
        target,
        composition=composition,
        component=adapter.identifier,
        prefix=prefix,
    )
    helpers["generate_model_description"](
        architecture,
        target,
        composition=composition,
        component=adapter.identifier,
        generation_time=None,
    )
    # An adapter has no step to declare.  pyfmi_sysml2 emits DefaultExperiment
    # when the composition authors start/stop control attributes; strip it so
    # the adapter document never advertises a fixed step.
    _strip_default_experiment(
        target / adapter.identifier / "modelDescription.xml"
    )

    _write(
        target / f"{adapter.stem}_model.cpp",
        render_adapter_hooks(adapter),
    )
    _write(target / "CMakeLists.txt", render_adapter_cmake(adapter))
    _write(target / "wire.json", render_adapter_wire_json(adapter))
    (target / "model.json").write_bytes(adapter_model_json(adapter))
    if adapter.serialization == "protobuf":
        _write(target / f"{adapter.wire_model.name}.proto", render_proto(adapter.wire_model))
    return target


# -- generated C++ ----------------------------------------------------------


def _signal_state_name(signal: AdapterSignal) -> str:
    return f"string_{signal.field}"


def _type_number(signal: AdapterSignal) -> int:
    return signal.data_type.number


def _cpp_value(signal: AdapterSignal, expression: str) -> str:
    if signal.data_type is DataType.REAL:
        return expression
    if signal.data_type is DataType.INTEGER:
        return f"static_cast<std::int32_t>({expression})"
    if signal.data_type is DataType.BOOLEAN:
        return expression
    return f"std::string(({expression}) != nullptr ? ({expression}) : \"\")"


def _packed_helpers() -> str:
    return r"""
void append_u32(std::string& out, std::uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<char>((value >> shift) & 0xFFu));
    }
}

void append_i32(std::string& out, std::int32_t value) {
    append_u32(out, static_cast<std::uint32_t>(value));
}

void append_double(std::string& out, double value) {
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    for (int shift = 0; shift < 64; shift += 8) {
        out.push_back(static_cast<char>((bits >> shift) & 0xFFu));
    }
}

void append_bool(std::string& out, bool value) {
    out.push_back(value ? '\1' : '\0');
}

bool read_u32(std::string_view payload, std::size_t& offset,
              std::uint32_t& out) {
    if (payload.size() - offset < 4u) {
        return false;
    }
    out = 0;
    for (int index = 0; index < 4; ++index) {
        out |= static_cast<std::uint32_t>(
                   static_cast<unsigned char>(payload[offset + index]))
               << (8 * index);
    }
    offset += 4u;
    return true;
}

bool read_i32(std::string_view payload, std::size_t& offset,
              std::int32_t& out) {
    std::uint32_t raw = 0;
    if (!read_u32(payload, offset, raw)) {
        return false;
    }
    std::memcpy(&out, &raw, sizeof(out));
    return true;
}

bool read_double(std::string_view payload, std::size_t& offset,
                 double& out) {
    if (payload.size() - offset < 8u) {
        return false;
    }
    std::uint64_t bits = 0;
    for (int index = 0; index < 8; ++index) {
        bits |= static_cast<std::uint64_t>(
                    static_cast<unsigned char>(payload[offset + index]))
                << (8 * index);
    }
    offset += 8u;
    std::memcpy(&out, &bits, sizeof(out));
    return true;
}

bool read_bool(std::string_view payload, std::size_t& offset, bool& out) {
    if (payload.size() - offset < 1u) {
        return false;
    }
    out = static_cast<unsigned char>(payload[offset]) != 0u;
    offset += 1u;
    return true;
}
"""


def _packed_encode(adapter: AdapterModel) -> str:
    lines = []
    for signal in adapter.wire_signals:
        member = f"model.{signal.member}"
        if signal.data_type is DataType.REAL:
            lines.append(f"    append_double(payload, {member});")
        elif signal.data_type is DataType.INTEGER:
            lines.append(f"    append_i32(payload, {member});")
        elif signal.data_type is DataType.BOOLEAN:
            lines.append(f"    append_bool(payload, {member});")
        else:
            lines.append(
                f"    const std::string text_{signal.field} =\n"
                f"        {member} != nullptr ? std::string({member}) : std::string();\n"
                f"    append_u32(payload, static_cast<std::uint32_t>(\n"
                f"        text_{signal.field}.size()));\n"
                f"    payload.append(text_{signal.field});"
            )
    return "\n".join(lines) if lines else "    (void)model;"


def _packed_decode(adapter: AdapterModel) -> str:
    lines = []
    for signal in adapter.wire_signals:
        member = f"model.{signal.member}"
        field = signal.field
        if signal.data_type is DataType.REAL:
            lines.append(
                f"    double value_{field} = 0.0;\n"
                f"    if (!read_double(payload, offset, value_{field})) {{\n"
                '        error = "packed payload is truncated";\n'
                "        return false;\n"
                "    }\n"
                f"    {member} = value_{field};"
            )
        elif signal.data_type is DataType.INTEGER:
            lines.append(
                f"    std::int32_t value_{field} = 0;\n"
                f"    if (!read_i32(payload, offset, value_{field})) {{\n"
                '        error = "packed payload is truncated";\n'
                "        return false;\n"
                "    }\n"
                f"    {member} = value_{field};"
            )
        elif signal.data_type is DataType.BOOLEAN:
            lines.append(
                f"    bool value_{field} = false;\n"
                f"    if (!read_bool(payload, offset, value_{field})) {{\n"
                '        error = "packed payload is truncated";\n'
                "        return false;\n"
                "    }\n"
                f"    {member} = value_{field};"
            )
        else:
            lines.append(
                f"    std::uint32_t length_{field} = 0;\n"
                f"    if (!read_u32(payload, offset, length_{field})) {{\n"
                '        error = "packed payload is truncated";\n'
                "        return false;\n"
                "    }\n"
                f"    if (length_{field} > {signal.capacity}u ||\n"
                f"        static_cast<std::size_t>(length_{field}) > payload.size() - offset) {{\n"
                '        error = "packed string exceeds capacity or payload";\n'
                "        return false;\n"
                "    }\n"
                f"    state.{_signal_state_name(signal)}.assign(\n"
                f"        payload.data() + offset, length_{field});\n"
                f"    {member} = state.{_signal_state_name(signal)}.c_str();\n"
                f"    offset += length_{field};"
            )
    return "\n".join(lines) if lines else "    (void)model;\n    (void)state;\n    (void)offset;"


_PB_KIND = {
    DataType.REAL: (1, "SetDouble", "GetDouble"),
    DataType.INTEGER: (2, "SetInt64", "GetInt64"),
    DataType.BOOLEAN: (3, "SetBool", "GetBool"),
    DataType.STRING: (4, "SetString", "GetString"),
}


def _pb_encode(adapter: AdapterModel, message: str) -> str:
    lines = []
    for signal in adapter.wire_signals:
        kind, setter, _ = _PB_KIND[signal.data_type]
        member = f"model.{signal.member}"
        value = _cpp_value(signal, member)
        lines.append(
            "    {\n"
            "        const google::protobuf::FieldDescriptor* field =\n"
            f"            message.GetDescriptor()->FindFieldByNumber({signal.field});\n"
            "        if (field == nullptr) {\n"
            f'            error = "payload field {signal.field} is missing";\n'
            "            return false;\n"
            "        }\n"
            "        google::protobuf::Message* value =\n"
            "            message.GetReflection()->MutableMessage(&message, field);\n"
            "        const google::protobuf::FieldDescriptor* kind =\n"
            f"            value->GetDescriptor()->FindFieldByNumber({kind});\n"
            f"        value->GetReflection()->{setter}(value, kind, {value});\n"
            "    }"
            if signal.data_type is DataType.STRING
            else "    {\n"
            "        const google::protobuf::FieldDescriptor* field =\n"
            f"            message.GetDescriptor()->FindFieldByNumber({signal.field});\n"
            "        if (field == nullptr) {\n"
            f'            error = "payload field {signal.field} is missing";\n'
            "            return false;\n"
            "        }\n"
            "        google::protobuf::Message* value =\n"
            "            message.GetReflection()->MutableMessage(&message, field);\n"
            "        const google::protobuf::FieldDescriptor* kind =\n"
            f"            value->GetDescriptor()->FindFieldByNumber({kind});\n"
            f"        value->GetReflection()->{setter}(value, kind, {value});\n"
            "    }"
        )
    return "\n".join(lines) if lines else "    (void)message;\n    (void)model;"


def _pb_decode(adapter: AdapterModel, message: str) -> str:
    lines = []
    for signal in adapter.wire_signals:
        kind, _, getter = _PB_KIND[signal.data_type]
        member = f"model.{signal.member}"
        if signal.data_type is DataType.STRING:
            assignment = (
                f"        state.{_signal_state_name(signal)} =\n"
                f"            value.GetReflection()->{getter}(value, kind);\n"
                f"        if (state.{_signal_state_name(signal)}.size() > {signal.capacity}u) {{\n"
                '            error = "protobuf string exceeds capacity";\n'
                "            return false;\n"
                "        }\n"
                f"        {member} = state.{_signal_state_name(signal)}.c_str();"
            )
        elif signal.data_type is DataType.INTEGER:
            assignment = (
                f"        {member} = static_cast<std::int32_t>(\n"
                f"            value.GetReflection()->{getter}(value, kind));"
            )
        else:
            assignment = f"        {member} = value.GetReflection()->{getter}(value, kind);"
        lines.append(
            "    {\n"
            "        const google::protobuf::FieldDescriptor* field =\n"
            f"            message.GetDescriptor()->FindFieldByNumber({signal.field});\n"
            "        if (field == nullptr) {\n"
            f'            error = "payload field {signal.field} is missing";\n'
            "            return false;\n"
            "        }\n"
            "        const google::protobuf::Message& value =\n"
            "            message.GetReflection()->GetMessage(message, field);\n"
            "        const google::protobuf::FieldDescriptor* kind =\n"
            f"            value.GetDescriptor()->FindFieldByNumber({kind});\n"
            + assignment
            + "\n    }"
        )
    return (
        "\n".join(lines)
        if lines
        else "    (void)message;\n    (void)model;\n    (void)state;"
    )


def _resolve_uri_source(adapter: AdapterModel) -> str:
    """Generated transport URI resolver, parameter-first or environment-only."""

    names = {item.name for item in adapter.parameters}
    if not names:
        return (
            """
std::string resolve_transport_uri(const @STEM@_Instance&,
                                  std::string& error) {
    const char* raw = std::getenv("PYFMI_INTEROP_TRANSPORT");
    std::string value = raw != nullptr ? std::string(raw) : std::string();
    const char* endpoint_raw = std::getenv("PYFMI_INTEROP_TRANSPORT_ENDPOINT");
    const std::string endpoint =
        endpoint_raw != nullptr ? std::string(endpoint_raw) : std::string();
    if (value.empty()) {
        value = "loopback";
    }
    if (value == "none") {
        error = "a transport role requires PYFMI_INTEROP_TRANSPORT to name a backend";
        return {};
    }
    if (value.find("://") == std::string::npos && !endpoint.empty()) {
        value += "://" + endpoint;
    }
    return value;
}
"""
        ).replace("@STEM@", adapter.stem)
    transport = "model.transport" if "transport" in names else '""'
    bind = "model.bind_address" if "bind_address" in names else '""'
    peer = "model.peer_address" if "peer_address" in names else '""'
    return f'''
std::string resolve_transport_uri(const {adapter.stem}_Instance& model,
                                  std::string& error) {{
    const std::string scheme = {transport};
    const std::string bind = {bind};
    const std::string peer = {peer};
    if (scheme.empty() || scheme == "loopback") {{
        return "loopback";
    }}
    if (scheme != "udp" && scheme != "tcp") {{
        error = "parameter 'transport' value '" + scheme +
                "' is not accepted; accepted values: loopback, udp, tcp";
        return {{}};
    }}
    if (bind.empty()) {{
        return "loopback";
    }}
    const std::size_t colon = bind.rfind(':');
    if (colon == std::string::npos || colon == 0u || colon + 1u >= bind.size()) {{
        error = "parameter 'bind_address' value '" + bind +
                "' is not a host:port address";
        return {{}};
    }}
    std::string uri = scheme + "://" + bind;
    if (!peer.empty()) {{
        uri += "?peer=" + peer;
    }}
    return uri;
}}
'''


def render_adapter_hooks(adapter: AdapterModel) -> str:
    """Return ``<stem>_model.cpp``: transport plus wire flow, no equations."""

    stem = adapter.stem
    instance = f"{stem}_Instance"
    protobuf = adapter.serialization == "protobuf"
    message = "pyfmi_interop::wire::" + message_identifier(
        adapter.wire_model.interface or adapter.wire_model.name
    )
    records = ", ".join(
        f"{{{signal.field}u, {_type_number(signal)}u}}"
        for signal in adapter.wire_signals
    )
    string_members = "\n".join(
        f"    std::string {_signal_state_name(signal)};"
        for signal in adapter.wire_signals
        if signal.data_type is DataType.STRING
    )
    if protobuf:
        payload_includes = f'#include "{adapter.wire_model.name}.pb.h"\n'
        payload_encode = (
            f"bool encode_payload(const {instance}& model, std::string& payload,\n"
            "                    std::string& error) {\n"
            f"    {message} message;\n"
            + _pb_encode(adapter, message)
            + "\n    payload = message.SerializeAsString();\n"
            "    error.clear();\n"
            "    return true;\n"
            "}\n\n"
            f"bool decode_payload({instance}& model, {stem}_State& state,\n"
            "                    std::string_view payload, std::string& error) {\n"
            "    error.clear();\n"
            f"    {message} message;\n"
            "    if (payload.size() >\n"
            "        static_cast<std::size_t>(std::numeric_limits<int>::max())) {\n"
            '        error = "payload is too large to parse";\n'
            "        return false;\n"
            "    }\n"
            "    if (!message.ParseFromArray(payload.data(),\n"
            "                                static_cast<int>(payload.size()))) {\n"
            f'        error = "payload is not a valid {message} message";\n'
            "        return false;\n"
            "    }\n"
            + _pb_decode(adapter, message)
            + "\n    return true;\n}"
        )
        packed_helpers = ""
    else:
        payload_includes = ""
        packed_helpers = _packed_helpers()
        payload_encode = (
            f"bool encode_payload(const {instance}& model, std::string& payload,\n"
            "                    std::string& error) {\n"
            "    error.clear();\n"
            "    payload.clear();\n"
            + _packed_encode(adapter)
            + "\n    return true;\n"
            "}\n\n"
            f"bool decode_payload({instance}& model, {stem}_State& state,\n"
            "                    std::string_view payload, std::string& error) {\n"
            "    error.clear();\n"
            "    std::size_t offset = 0;\n"
            + _packed_decode(adapter)
            + "\n    if (offset != payload.size()) {\n"
            '        error = "packed payload has trailing bytes";\n'
            "        return false;\n"
            "    }\n"
            "    return true;\n}"
        )

    format = "Protobuf" if protobuf else "Packed"
    role = adapter.role
    receive = role in ("receiver", "adapter")
    publish = role in ("sender", "adapter")
    step_body = []
    if role == "none":
        step_body.append("    (void)current_communication_point;")
    else:
        step_body.append(
            "    auto* state = state_of(instance);\n"
            "    if (state == nullptr || state->transport == nullptr) {\n"
            "        return fmi2Error;\n"
            "    }"
        )
        if receive:
            step_body.append("    receive_and_apply(*instance, *state);")
        if publish:
            step_body.append(
                f"""    std::string error;
    state->payload.clear();
    if (!encode_payload(*instance, state->payload, error)) {{
        std::fprintf(stderr, "pyfmi_interop: encode failed: %s\\n", error.c_str());
        return fmi2Error;
    }}
    const double nanoseconds =
        current_communication_point > 0.0
            ? current_communication_point * 1e9
            : 0.0;
    pyfmi_interop::wire::EncodeResult encoded =
        pyfmi_interop::wire::encode_frame(
            wire_model_id(), state->payload, state->instance_id,
            state->sequence + 1, static_cast<std::uint64_t>(nanoseconds),
            pyfmi_interop::wire::PayloadFormat::{format});
    if (!encoded) {{
        std::fprintf(stderr, "pyfmi_interop: frame encode failed: %s\\n",
                     encoded.error.message.c_str());
        return fmi2Error;
    }}
    ++state->sequence;
    const pyfmi_interop::ByteSpan bytes(
        reinterpret_cast<const std::byte*>(encoded.frame.data()),
        encoded.frame.size());
    try {{
        (void)state->transport->send(bytes);
    }} catch (const std::exception& error_send) {{
        std::fprintf(stderr, "pyfmi_interop: send failed: %s\\n",
                     error_send.what());
        return fmi2Error;
    }}"""
            )

    wire_top = '''
std::uint32_t instance_identity(const void* instance) {
    const std::uintptr_t raw = reinterpret_cast<std::uintptr_t>(instance);
    std::uint32_t hash = 2166136261u;
    for (std::size_t index = 0; index < sizeof(raw); ++index) {
        hash ^= static_cast<std::uint8_t>((raw >> (8u * index)) & 0xFFu);
        hash *= 16777619u;
    }
    return hash == 0u ? 1u : hash;
}
'''
    if role != "none":
        wire_top += f'''
const std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize>&
wire_model_id() {{
    static const std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize> id =
        pyfmi_interop::wire::model_id(
            std::string_view(kModelName),
            std::vector<pyfmi_interop::wire::ModelIdSignal>{{{records}}});
    return id;
}}
'''

    receive_function = ""
    if role != "none":
        receive_function = f'''
void receive_and_apply({instance}& model, {stem}_State& state) {{
    if (state.transport == nullptr) {{
        return;
    }}
    std::optional<std::vector<std::byte>> frame;
    try {{
        frame = state.transport->receive();
    }} catch (const std::exception&) {{
        state.transport->record_format_error();
        return;
    }}
    if (!frame) {{
        return;
    }}
    const std::string_view buffer(
        reinterpret_cast<const char*>(frame->data()), frame->size());
    const pyfmi_interop::wire::DecodeResult decoded =
        pyfmi_interop::wire::decode_frame(buffer);
    if (!decoded) {{
        state.transport->record_format_error();
        return;
    }}
    if (decoded.frame.header.model_id != wire_model_id()) {{
        state.transport->record_model_id_mismatch();
        return;
    }}
    if (decoded.frame.header.payload_format !=
        pyfmi_interop::wire::PayloadFormat::{format}) {{
        state.transport->record_format_error();
        return;
    }}
    const std::string_view payload(
        reinterpret_cast<const char*>(decoded.frame.payload.data()),
        decoded.frame.payload.size());
    std::string error;
    if (!decode_payload(model, state, payload, error)) {{
        state.transport->record_format_error();
        std::fprintf(stderr, "pyfmi_interop: decode failed: %s\\n",
                     error.c_str());
    }}
}}
'''

    uri_source = _resolve_uri_source(adapter) if role != "none" else ""
    initialize_transport = ""
    if role != "none":
        initialize_transport = '''
    std::string error;
    const std::string uri = resolve_transport_uri(*instance, error);
    if (uri.empty()) {
        std::fprintf(stderr, "pyfmi_interop: %s\\n", error.c_str());
        return fmi2Error;
    }
    try {
        std::unique_ptr<pyfmi_interop::Transport> transport =
            pyfmi_interop::make_transport(uri);
        transport->initialize(uri);
        state->transport = std::move(transport);
    } catch (const std::exception& transport_error) {
        std::fprintf(stderr, "pyfmi_interop: transport '%s' failed: %s\\n",
                     uri.c_str(), transport_error.what());
        return fmi2Error;
    }
'''

    return f"""// Generated by pyfmi-interop (psysml2 FMI layer). Do not edit by hand.
//
// FMI 2.0 plumbing is generated by pyfmi_sysml2; this file supplies the five
// model hooks.  The adapter carries values to and from the wire and has no
// equations.
#include "{stem}_hooks.h"

#include "pyfmi_interop/runtime/transport.hpp"
#include "pyfmi_interop/runtime/wire.hpp"

{payload_includes}#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {{

constexpr char kModelName[] = "{adapter.wire_model.name}";

struct {stem}_State {{
    std::unique_ptr<pyfmi_interop::Transport> transport;
    std::uint32_t instance_id = 0;
    std::uint64_t sequence = 0;
    std::string payload;
{string_members}
}};

{stem}_State* state_of({instance}* instance) {{
    return static_cast<{stem}_State*>(instance->user_data);
}}
{wire_top}{packed_helpers}{payload_encode}

{receive_function}
{uri_source}

}}  // namespace

fmi2Status {stem}_model_initialize({instance}* instance) {{
    if (instance == nullptr) {{
        return fmi2Error;
    }}
    auto* state = state_of(instance);
    if (state == nullptr) {{
        state = new (std::nothrow) {stem}_State{{}};
        if (state == nullptr) {{
            return fmi2Error;
        }}
        state->instance_id = instance_identity(instance);
        instance->user_data = state;
    }}
    if (state->transport) {{
        state->transport->finalize();
        state->transport.reset();
    }}
    state->sequence = 0;
    state->payload.clear();
{initialize_transport}
    return fmi2OK;
}}

fmi2Status {stem}_model_do_step(
    {instance}* instance, fmi2Real current_communication_point,
    fmi2Real communication_step_size) {{
    (void)communication_step_size;
    if (instance == nullptr) {{
        return fmi2Error;
    }}
{chr(10).join(step_body)}
    return fmi2OK;
}}

fmi2Status {stem}_model_terminate({instance}* instance) {{
    if (instance == nullptr) {{
        return fmi2OK;
    }}
    auto* state = state_of(instance);
    if (state != nullptr && state->transport) {{
        state->transport->finalize();
        state->transport.reset();
    }}
    return fmi2OK;
}}

fmi2Status {stem}_model_reset({instance}* instance) {{
    if (instance == nullptr) {{
        return fmi2OK;
    }}
    auto* state = state_of(instance);
    if (state != nullptr) {{
        if (state->transport) {{
            state->transport->finalize();
            state->transport.reset();
        }}
        state->sequence = 0;
        state->payload.clear();
    }}
    return fmi2OK;
}}

fmi2Status {stem}_model_free({instance}* instance) {{
    if (instance == nullptr) {{
        return fmi2OK;
    }}
    auto* state = state_of(instance);
    if (state != nullptr) {{
        if (state->transport) {{
            state->transport->finalize();
        }}
        delete state;
        instance->user_data = nullptr;
    }}
    return fmi2OK;
}}
"""


def render_adapter_cmake(adapter: AdapterModel) -> str:
    """Return the CMake project compiling the two generated translation units."""

    protobuf = adapter.serialization == "protobuf"
    proto = ""
    if protobuf:
        proto = f"""
pyfmi_interop_wire_add_proto(
    {adapter.identifier}
    "${{CMAKE_CURRENT_SOURCE_DIR}}/{adapter.wire_model.name}.proto"
)
"""
    return f"""cmake_minimum_required(VERSION 3.16)
project({adapter.identifier} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(
    PYFMI_INTEROP_RUNTIME_INCLUDE_DIR
    ""
    CACHE PATH
    "Directory containing pyfmi_interop/runtime/*.hpp"
)
set(
    PYFMI_INTEROP_RUNTIME_LIBRARY
    ""
    CACHE FILEPATH
    "Path to the static pyfmi-interop runtime library"
)
set(
    PYFMI_INTEROP_CMAKE_DIR
    ""
    CACHE PATH
    "Directory containing the shared wire.cmake module"
)
set(
    PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR
    ""
    CACHE PATH
    "Directory containing pyfmi_interop/transport/*.hpp"
)
set(
    PYFMI_INTEROP_TRANSPORT_LIBRARY
    ""
    CACHE FILEPATH
    "Path to the static pyfmi-interop transport library"
)

if(NOT PYFMI_INTEROP_CMAKE_DIR)
    message(FATAL_ERROR "PYFMI_INTEROP_CMAKE_DIR is required")
endif()
include("${{PYFMI_INTEROP_CMAKE_DIR}}/wire.cmake")
pyfmi_interop_resolve_wire()

find_package(Threads REQUIRED)

add_library(
    {adapter.identifier}
    SHARED
    {adapter.stem}_fmi.cpp
    {adapter.stem}_model.cpp
)
target_compile_features({adapter.identifier} PRIVATE cxx_std_17)
target_include_directories(
    {adapter.identifier}
    PRIVATE
    "${{CMAKE_CURRENT_SOURCE_DIR}}"
    "${{PYFMI_INTEROP_RUNTIME_INCLUDE_DIR}}"
    "${{PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR}}"
)
pyfmi_interop_configure_wire({adapter.identifier})
{proto}
# The psysml2 runtime owns the FMI C ABI, so interop's facade object must not be
# pulled from the runtime archive: link it without whole-archive.
target_link_libraries({adapter.identifier} PRIVATE "${{PYFMI_INTEROP_RUNTIME_LIBRARY}}")
if(MSVC)
    target_link_options(
        {adapter.identifier}
        PRIVATE
        "/WHOLEARCHIVE:${{PYFMI_INTEROP_TRANSPORT_LIBRARY}}"
    )
elseif(APPLE)
    target_link_libraries(
        {adapter.identifier}
        PRIVATE
        "-Wl,-force_load,${{PYFMI_INTEROP_TRANSPORT_LIBRARY}}"
    )
else()
    target_link_libraries(
        {adapter.identifier}
        PRIVATE
        "-Wl,--whole-archive"
        "${{PYFMI_INTEROP_TRANSPORT_LIBRARY}}"
        "-Wl,--no-whole-archive"
    )
endif()
target_link_libraries({adapter.identifier} PRIVATE Threads::Threads)

set_target_properties(
    {adapter.identifier}
    PROPERTIES
    OUTPUT_NAME "{adapter.identifier}"
    POSITION_INDEPENDENT_CODE ON
)
"""
