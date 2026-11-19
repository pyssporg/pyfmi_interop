"""Realtime FMI generation, build and packaging for distributed simulation.

The public surface is the IR (:mod:`pyfmi_interop.ir`), the adapter
catalogue (:mod:`pyfmi_interop.adapters`), the C++ generator
(:mod:`pyfmi_interop.codegen`), the native build driver
(:mod:`pyfmi_interop.builder`), the FMU packager
(:mod:`pyfmi_interop.packaging`), and the ``pyfmi-interop`` CLI.

``timing`` and ``sysml`` are imported lazily: the SysML ingestion path depends
on optional packages, and importing them must not make the runtime/codegen path
unusable.
"""

from __future__ import annotations

import importlib
from typing import Any

from . import adapters, builder, codegen, ir, native, packaging
from .adapters import (
    ADAPTERS,
    AdapterDescriptor,
    adapter_cmake_flags,
    available_adapters,
    get_adapter,
    require_adapter,
)
from .builder import build_model
from .codegen import generate_model
from .ir import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
    TransportBinding,
    assign_value_references,
    deterministic_guid,
    fingerprint,
    model_from_dict,
    model_to_dict,
    write_model_json,
)
from .packaging import package_fmu

__version__ = "0.2.0"

_LAZY_MODULES = {
    "sysml": ".sysml",
    "timing": ".timing",
}

__all__ = [
    "ADAPTERS",
    "AdapterDescriptor",
    "DataType",
    "Direction",
    "ModelDefinition",
    "RateGroup",
    "Signal",
    "TransportBinding",
    "__version__",
    "adapter_cmake_flags",
    "adapters",
    "assign_value_references",
    "available_adapters",
    "build_model",
    "builder",
    "codegen",
    "deterministic_guid",
    "fingerprint",
    "generate_model",
    "get_adapter",
    "ir",
    "model_from_dict",
    "model_to_dict",
    "native",
    "package_fmu",
    "packaging",
    "require_adapter",
    "sysml",
    "timing",
    "write_model_json",
]


def __getattr__(name: str) -> Any:
    module = _LAZY_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return importlib.import_module(module, __name__)


def __dir__() -> list[str]:
    return sorted(set(__all__))
