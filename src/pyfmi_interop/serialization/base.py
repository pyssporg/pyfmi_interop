"""The serialization backend contract.

A backend owns two artifacts: the schema bundle it ships next to the model,
and the generated codec source that turns model values into its payload.  The
framing layer above both is :mod:`pyfmi_interop.wire`; a backend never writes
frame bytes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Mapping

from ..ir import ModelDefinition
from .naming import message_identifier

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
    packager can add artifacts without touching the filesystem; a key may be an
    absolute path for a schema the backend keeps outside the emitted tree.

    The remaining methods are the out-of-tree seam.  A backend declares the
    payload identity written to ``wire.json`` and any extra CMake inputs its
    own codec and schema need.  Every method has a default, so a backend that
    declares nothing keeps the built-in output: the payload message is the
    sanitized interface name, the proto package is absent, and the generated
    project compiles only this repository's runtime and bindings.
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
        The method receives the whole model and the resolved role, so a backend
        may emit arbitrary code from those inputs.
        """

    def payload_message(self, model: ModelDefinition) -> str:
        """Return the ``wire.json`` payload message full name."""

        return message_identifier(model.interface or model.name)

    def proto_package(self, model: ModelDefinition) -> str | None:
        """Return the ``wire.json`` proto package, or ``None`` when not proto3."""

        return None

    def cmake_proto_sources(self, model: ModelDefinition) -> Sequence[str]:
        """Return extra ``.proto`` sources compiled into the generated target."""

        return ()

    def cmake_proto_import_roots(self, model: ModelDefinition) -> Sequence[str]:
        """Return protoc import roots for :meth:`cmake_proto_sources`."""

        return ()

    def cmake_include_dirs(self, model: ModelDefinition) -> Sequence[str]:
        """Return extra include directories for the generated target."""

        return ()

    def cmake_link_libraries(self, model: ModelDefinition) -> Sequence[str]:
        """Return extra link libraries or CMake targets for the generated target."""

        return ()

    def emit_schema(self, model: ModelDefinition, out: str | Path) -> list[Path]:
        """Write :meth:`schema_files` into ``out`` and return their paths."""

        return write_files(out, self.schema_files(model))
