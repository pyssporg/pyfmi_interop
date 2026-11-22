"""Core model contract: specification, build configuration, compilation.

This package is SysML-free: the IR, timing, wire framing, serialization
backends, code generation, native build and packaging all live here.
"""

from __future__ import annotations

from .adapter import (
    AdapterModel,
    AdapterSignal,
    adapter_from_reduction,
    adapter_model_json,
    load_adapter_model,
    render_adapter_cmake,
    render_adapter_hooks,
    render_adapter_wire_json,
    wire_model_from_adapter_json,
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
    "DataType",
    "Direction",
    "ModelDefinition",
    "ModelSpec",
    "ProjectionError",
    "RateGroup",
    "Signal",
    "adapter_from_reduction",
    "adapter_model_json",
    "build_model",
    "compile_model",
    "generate_model",
    "load_adapter_model",
    "package_fmu",
    "render_adapter_cmake",
    "render_adapter_hooks",
    "render_adapter_wire_json",
    "wire_model_from_adapter_json",
]
