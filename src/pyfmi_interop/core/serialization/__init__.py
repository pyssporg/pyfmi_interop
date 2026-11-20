"""Serialization backends: protobuf, packed, and opaque.

The registry is the seam the CLI and the generator use.  Importing this module
registers the three built-in backends exactly once; third-party code may add
more with :func:`~.registry.register`.
"""

from __future__ import annotations

from . import opaque, packed, protobuf
from .base import Serialization, write_files
from .registry import get, names, register

__all__ = [
    "Serialization",
    "get",
    "names",
    "opaque",
    "packed",
    "protobuf",
    "register",
    "write_files",
]

register(protobuf.backend)
register(packed.backend)
register(opaque.backend)
