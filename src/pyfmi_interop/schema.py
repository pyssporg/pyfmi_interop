"""Backwards-compatible facade over the serialization backends.

Historically this module owned the protobuf emitter.  The emitter now lives in
:mod:`pyfmi_interop.serialization.protobuf`; this module keeps the public names
(``build_schema``, ``render_proto``, ``render_wire_json``, ``schema_entries``,
``write_schema``, ``payload_message_name``, ...) working and adds a
``serialization=`` selector for the packed and opaque backends.

Only the selected backend's artifacts are returned.  A packed or opaque model
therefore ships a ``wire.json`` without a ``.proto`` it never emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .ir import ModelDefinition
from .serialization import get
from .serialization.descriptor import (
    SCHEMA_FORMAT_VERSION,
    WIRE_JSON_NAME,
)
from .serialization.descriptor import (
    render_wire_json as _render_wire_json,
)
from .serialization.protobuf import (
    PROTO_PACKAGE,
    payload_message_name,
    proto_filename,
    render_proto,
)

__all__ = [
    "PROTO_PACKAGE",
    "SCHEMA_FORMAT_VERSION",
    "WIRE_JSON_NAME",
    "SchemaBundle",
    "build_schema",
    "payload_message_name",
    "proto_filename",
    "render_proto",
    "render_wire_json",
    "schema_entries",
    "write_schema",
]


@dataclass(frozen=True)
class SchemaBundle:
    """The artifacts projected from one model by one backend."""

    serialization: str
    format_id: int
    artifacts: Mapping[str, bytes]
    proto_name: str | None
    proto: bytes | None
    wire_json_name: str
    wire_json: bytes


def render_wire_json(
    model: ModelDefinition, *, serialization: str = "protobuf"
) -> str:
    """Return the deterministic JSON descriptor for ``model``."""

    backend = get(serialization)
    return _render_wire_json(
        model, serialization=backend.name, format_id=backend.format_id
    )


def build_schema(
    model: ModelDefinition, *, serialization: str = "protobuf"
) -> SchemaBundle:
    """Project ``model`` onto the artifacts of ``serialization``."""

    backend = get(serialization)
    artifacts = backend.schema_files(model)
    proto_name = proto_filename(model) if backend.name == "protobuf" else None
    return SchemaBundle(
        serialization=backend.name,
        format_id=backend.format_id,
        artifacts=artifacts,
        proto_name=proto_name,
        proto=artifacts.get(proto_name) if proto_name is not None else None,
        wire_json_name=WIRE_JSON_NAME,
        wire_json=artifacts[WIRE_JSON_NAME],
    )


def schema_entries(
    model: ModelDefinition,
    *,
    prefix: str | None = None,
    serialization: str = "protobuf",
) -> dict[str, bytes]:
    """Return ``{archive name: bytes}`` for the backend's artifacts."""

    bundle = build_schema(model, serialization=serialization)
    names: Iterable[tuple[str, bytes]] = sorted(bundle.artifacts.items())
    if prefix is None:
        return dict(names)
    base = prefix.strip("/")
    return {f"{base}/{name}": data for name, data in names}


def write_schema(
    model: ModelDefinition,
    directory: str | Path,
    *,
    serialization: str = "protobuf",
) -> tuple[Path, ...]:
    """Write the backend's artifacts into ``directory`` and return their paths."""

    return tuple(get(serialization).emit_schema(model, directory))
