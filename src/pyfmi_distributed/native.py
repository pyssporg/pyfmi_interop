"""Locations of the bundled native runtime and of a source-tree build.

The wheel ships a prebuilt static runtime plus its public headers.  A source
checkout builds them with CMake into ``build/runtime``.  Both lookup orders are
centralised here so ``setup.py``, the generator and the tests agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = [
    "RUNTIME_LIBRARY_NAME",
    "bundled_cmake_dir",
    "bundled_include_dir",
    "bundled_library_path",
    "cmake_module_dir",
    "default_runtime_library_path",
    "runtime_include_dirs",
    "runtime_library_name",
    "runtime_search_paths",
]

RUNTIME_LIBRARY_NAME = "pyfmi_distributed_runtime"


def runtime_library_name() -> str:
    if sys.platform == "win32":
        return f"{RUNTIME_LIBRARY_NAME}.lib"
    return f"lib{RUNTIME_LIBRARY_NAME}.a"


def bundled_include_dir() -> Path:
    return Path(__file__).resolve().parent / "_runtime" / "include"


def bundled_library_path() -> Path:
    return Path(__file__).resolve().parent / "_runtime" / runtime_library_name()


def bundled_cmake_dir() -> Path:
    """CMake modules bundled into the wheel (``adapters.cmake`` lives here)."""

    return Path(__file__).resolve().parent / "_runtime" / "cmake"


def cmake_module_dir(repo_root: Path | None = None) -> Path:
    """Return the directory holding the shared ``adapters.cmake`` module.

    A source checkout is preferred over the wheel copy so development builds
    use the current CMake logic.
    """

    source_candidates: list[Path] = []
    if repo_root is not None:
        source_candidates.append(Path(repo_root) / "cmake")
    bundled = bundled_cmake_dir()
    source_candidates.append(bundled)

    for candidate in source_candidates:
        if (candidate / "adapters.cmake").is_file():
            return candidate

    searched = ", ".join(str(path) for path in source_candidates)
    raise FileNotFoundError(
        f"cmake/adapters.cmake not found (searched: {searched})"
    )


def default_runtime_library_path(repo_root: Path) -> Path:
    """Static library produced by the top-level CMake build."""

    return Path(repo_root) / "build" / "runtime" / runtime_library_name()


def runtime_search_paths(repo_root: Path | None = None) -> list[Path]:
    """Return candidate library paths in precedence order."""

    candidates = [bundled_library_path()]
    if repo_root is not None:
        candidates.append(default_runtime_library_path(Path(repo_root)))
    return candidates


def runtime_include_dirs(repo_root: Path | None = None) -> list[Path]:
    """Return include directories that expose ``pyfmi_distributed/runtime/*``."""

    candidates: list[Path] = []
    bundled = bundled_include_dir()
    if bundled.is_dir():
        candidates.append(bundled)
    if repo_root is not None:
        source_include = Path(repo_root) / "runtime" / "include"
        if source_include.is_dir():
            candidates.append(source_include)
    return candidates
