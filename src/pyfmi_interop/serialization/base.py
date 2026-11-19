"""The serialization backend contract.

A backend owns two artifacts: the schema bundle it ships next to the model,
and the generated codec source that turns model values into its payload.  The
framing layer above both is :mod:`pyfmi_interop.wire`; a backend never writes
frame bytes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Mapping

from ..ir import ModelDefinition

__all__ = ["Serialization", "write_files"]


def write_files(target: str | Path, files: Mapping[str, bytes | str]) -> list[Path]:
    """Write ``files`` under ``target`` in sorted-name order and return paths."""

    directory = Path(target)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(files):
        data = files[name]
        path = directory / name
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8", newline="\n")
        else:
            path.write_bytes(data)
        written.append(path)
    return written


class Serialization(ABC):
    """One payload serialization backend.

    ``name`` is the CLI value, ``format_id`` is the uint16 carried in the wire
    envelope's ``payload_format`` field (``0`` opaque, ``1`` protobuf, ``2``
    packed).  ``schema_files`` is the in-memory form of ``emit_schema`` so the
    packager can add artifacts without touching the filesystem.
    """

    name: str
    format_id: int

    @abstractmethod
    def schema_files(self, model: ModelDefinition) -> dict[str, bytes]:
        """Return ``{filename: bytes}`` for every artifact this backend emits."""

    @abstractmethod
    def generate_codec(
        self, model: ModelDefinition, out: str | Path, role: str
    ) -> list[Path]:
        """Write the backend's codec sources and return their paths.

        An opaque or not-yet-implemented native codec returns an empty list;
        the model source tree then compiles without a payload translation unit.
        """

    def emit_schema(self, model: ModelDefinition, out: str | Path) -> list[Path]:
        """Write :meth:`schema_files` into ``out`` and return their paths."""

        return write_files(out, self.schema_files(model))
