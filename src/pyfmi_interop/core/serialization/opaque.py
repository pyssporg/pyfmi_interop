"""Opaque payload backend: no schema, no codec, bytes pass through.

The user's ``user_step`` (or an external producer) supplies the payload; this
repository only frames it.  ``format_id`` is ``0`` so a decoder can tell an
opaque frame from protobuf (``1``) or packed (``2``).
"""

from __future__ import annotations

from pathlib import Path

from ..ir import ModelDefinition
from .base import Serialization
from .descriptor import WIRE_JSON_NAME, wire_json_bytes

__all__ = ["OpaqueSerialization", "backend", "decode", "encode"]

_FORMAT_ID = 0


def encode(payload: bytes | bytearray | memoryview) -> bytes:
    """Return the caller's bytes unchanged."""

    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("opaque payload must be bytes-like")
    return bytes(payload)


def decode(payload: bytes | bytearray | memoryview) -> bytes:
    """Return the caller's bytes unchanged."""

    return encode(payload)


class OpaqueSerialization(Serialization):
    """No schema and no generated codec; the payload is caller bytes."""

    name = "opaque"
    format_id = _FORMAT_ID

    def schema_files(self, model: ModelDefinition) -> dict[str, bytes]:
        # No ``.proto`` and no codec: the descriptor is the only artifact.
        return {
            WIRE_JSON_NAME: wire_json_bytes(
                model, serialization=self.name, format_id=self.format_id
            )
        }

    def generate_codec(
        self, model: ModelDefinition, out: str | Path, role: str
    ) -> list[Path]:
        return []


backend = OpaqueSerialization()
