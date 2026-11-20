"""Locations of the bundled SysML definitions.

The wheel ships the reusable ``PyfmiInterop`` vocabulary as package data.  A
source checkout reads the same file next to this module, so ``load_model`` and
the ``psysml2`` generation path agree on one include root.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

__all__ = ["interop_definitions", "load_with_interop"]


def interop_definitions() -> Path:
    """Return the bundled ``PyfmiInterop`` SysML library as a real path."""

    return Path(__file__).resolve().parent / "interop.sysml"


def load_with_interop(
    source: Any, load: Any, includes: Iterable[str | Path] = ()
) -> Any:
    """Load ``source`` plus caller roots, adding the library only when imported.

    ``includes`` are extra package roots the caller supplies (a library a model
    imports); they are passed to every load call so the first parse resolves
    those imports.  The bundled vocabulary is an include root, not a definition
    every model inherits.  ``pyfmi_sysml2`` selects an export unit by
    ``:> FmuModel``, so including the library in an architecture that never
    imports it would expose ``FmuInterop`` as a candidate and change that
    model's composition.  The model declares ``PyfmiInterop`` in its imports
    only when it wants the shared types, so the include is conditional on that
    declaration; an imported package root can make that declaration visible
    too, so the check runs after the caller's roots are loaded.
    """

    roots = tuple(includes)
    architecture = load(source, *roots)
    if "PyfmiInterop" not in getattr(architecture, "imports", {}):
        return architecture
    return load(source, *roots, interop_definitions())
