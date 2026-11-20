"""Core model contract: specification, build configuration, compilation.

This package is SysML-free: the IR, timing, wire framing, serialization
backends, code generation, native build and packaging all live here.
"""

from __future__ import annotations

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
    "BuildConfig",
    "Compilation",
    "DataType",
    "Direction",
    "ModelDefinition",
    "ModelSpec",
    "ProjectionError",
    "RateGroup",
    "Signal",
    "build_model",
    "compile_model",
    "generate_model",
    "package_fmu",
]
