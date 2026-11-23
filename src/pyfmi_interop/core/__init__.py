"""Core model contract: specification, build configuration, compilation.

This package is independent of any source dialect: the IR, timing, wire
framing, serialization backends, code generation, native build and packaging
all live here.
"""

from __future__ import annotations

from .adapter import (
    FMI_LAYER,
    AdapterModel,
    AdapterSignal,
    adapter_from_reduction,
    adapter_model_json,
    load_adapter_model,
    render_adapter_cmake,
    render_adapter_hooks,
    render_adapter_wire_json,
    require_fmi_layer,
    select_component,
    wire_model_from_adapter_json,
    write_adapter_tree,
)
from .attributes import (
    DEFAULT_STEP_SIZE_S,
    DEFAULT_STRING_CAPACITY,
    data_type_from_name,
    direction_from_causality,
    model_name,
    period_seconds_from_attributes,
    rate_hz_from_attributes,
    sanitize_identifier,
    signal_from_values,
    step_size_for_scopes,
    step_size_from_attributes,
    string_capacity,
    unit_from_attributes,
)
from .builder import build_model
from .codegen import generate_model
from .ir import (
    DataType,
    Direction,
    ModelDefinition,
    ProjectionError,
    RateGroup,
    Signal,
)
from .packaging import package_fmu
from .pipeline import Compilation, compile_model
from .spec import BuildConfig, ModelSpec

__all__ = [
    "AdapterModel",
    "AdapterSignal",
    "BuildConfig",
    "Compilation",
    "DEFAULT_STEP_SIZE_S",
    "DEFAULT_STRING_CAPACITY",
    "DataType",
    "Direction",
    "FMI_LAYER",
    "ModelDefinition",
    "ModelSpec",
    "ProjectionError",
    "RateGroup",
    "Signal",
    "adapter_from_reduction",
    "adapter_model_json",
    "build_model",
    "compile_model",
    "data_type_from_name",
    "direction_from_causality",
    "generate_model",
    "load_adapter_model",
    "model_name",
    "package_fmu",
    "period_seconds_from_attributes",
    "rate_hz_from_attributes",
    "render_adapter_cmake",
    "render_adapter_hooks",
    "render_adapter_wire_json",
    "require_fmi_layer",
    "sanitize_identifier",
    "select_component",
    "signal_from_values",
    "step_size_for_scopes",
    "step_size_from_attributes",
    "string_capacity",
    "unit_from_attributes",
    "wire_model_from_adapter_json",
    "write_adapter_tree",
]
