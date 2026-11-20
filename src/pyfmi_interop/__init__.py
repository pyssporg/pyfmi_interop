"""Realtime FMI generation, build and packaging for the wire contract.

The public surface is the IR (:mod:`pyfmi_interop.ir`), the wire envelope
(:mod:`pyfmi_interop.wire`), the schema emitter
(:mod:`pyfmi_interop.schema`), the C++ generator
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

from . import builder, codegen, ir, native, packaging, roles, schema, serialization, wire
from .builder import build_model
from .codegen import generate_model
from .core import BuildConfig, Compilation, ModelSpec, compile_model
from .definitions import interop_definitions
from .ir import (
    DataType,
    Direction,
    ModelDefinition,
    ProjectionError,
    RateGroup,
    Signal,
    assign_value_references,
    deterministic_guid,
    encode_string,
    fingerprint,
    model_from_dict,
    model_to_dict,
    write_model_json,
)
from .packaging import package_fmu
from .roles import derive_role, resolve_role
from .schema import (
    build_schema,
    render_proto,
    render_wire_json,
    schema_entries,
    write_schema,
)
from .wire import (
    HEADER_SIZE,
    WIRE_VERSION,
    ChecksumError,
    DecodedFrame,
    FieldRangeError,
    Header,
    HeaderChecksumError,
    InvalidFlags,
    InvalidHeaderSize,
    InvalidMagic,
    InvalidReserved,
    LengthOverflow,
    NonZeroFlags,
    NonZeroReserved,
    PayloadChecksumError,
    PayloadFormat,
    TrailingBytes,
    TruncatedFrame,
    UnsupportedPayloadFormat,
    UnsupportedWireVersion,
    WireError,
    decode,
    encode,
    model_id,
)

__version__ = "0.5.0"

_LAZY_MODULES = {
    "psysml2": ".psysml2",
    "sysml": ".sysml",
    "timing": ".timing",
}

__all__ = [
    "BuildConfig",
    "ChecksumError",
    "Compilation",
    "DataType",
    "DecodedFrame",
    "Direction",
    "FieldRangeError",
    "HEADER_SIZE",
    "Header",
    "HeaderChecksumError",
    "InvalidFlags",
    "InvalidHeaderSize",
    "InvalidMagic",
    "InvalidReserved",
    "LengthOverflow",
    "NonZeroFlags",
    "NonZeroReserved",
    "ModelDefinition",
    "ModelSpec",
    "PayloadChecksumError",
    "PayloadFormat",
    "ProjectionError",
    "RateGroup",
    "Signal",
    "TrailingBytes",
    "TruncatedFrame",
    "UnsupportedPayloadFormat",
    "UnsupportedWireVersion",
    "WIRE_VERSION",
    "WireError",
    "__version__",
    "assign_value_references",
    "build_model",
    "build_schema",
    "builder",
    "codegen",
    "compile_model",
    "decode",
    "derive_role",
    "deterministic_guid",
    "encode",
    "encode_string",
    "fingerprint",
    "generate_model",
    "interop_definitions",
    "ir",
    "model_from_dict",
    "model_id",
    "model_to_dict",
    "native",
    "package_fmu",
    "packaging",
    "psysml2",
    "render_proto",
    "render_wire_json",
    "resolve_role",
    "roles",
    "schema",
    "schema_entries",
    "serialization",
    "sysml",
    "timing",
    "wire",
    "write_model_json",
    "write_schema",
]


def __getattr__(name: str) -> Any:
    module = _LAZY_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return importlib.import_module(module, __name__)


def __dir__() -> list[str]:
    return sorted(set(__all__))
