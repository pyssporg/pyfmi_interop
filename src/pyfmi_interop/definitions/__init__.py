"""Compatibility facade: the bundled definitions now live under ``sysml``."""

from __future__ import annotations

from ..sysml.definitions import interop_definitions, load_with_interop

__all__ = ["interop_definitions", "load_with_interop"]
