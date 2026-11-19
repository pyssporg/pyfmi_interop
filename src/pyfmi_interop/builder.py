"""Build a generated model source tree into a shared library.

The Python layer owns CMake invocation so the CLI, the tests, and downstream
build tools agree on generator selection, runtime resolution, and error
reporting.  CMake output is captured and re-raised with the failing command so
a build failure is diagnosable from the CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from . import native

__all__ = [
    "build_model",
    "resolve_runtime_include",
    "resolve_runtime_library",
    "resolve_transport_include",
    "resolve_transport_library",
]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_runtime_library(runtime_library: str | Path | None = None) -> Path:
    """Return the static runtime library to link against."""

    if runtime_library is not None:
        candidate = Path(runtime_library)
        if not candidate.is_file():
            raise FileNotFoundError(f"runtime library does not exist: {candidate}")
        return candidate

    candidates = [
        native.bundled_library_path(),
        native.default_runtime_library_path(_REPO_ROOT),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "runtime library not found (searched: "
        f"{searched}). Build the native runtime or install a wheel that bundles it."
    )


def resolve_runtime_include(runtime_include: str | Path | None = None) -> Path:
    """Return the directory that exposes ``pyfmi_interop/runtime/*``."""

    if runtime_include is not None:
        candidate = Path(runtime_include)
        if not candidate.is_dir():
            raise FileNotFoundError(f"runtime include directory does not exist: {candidate}")
        return candidate

    candidates = native.runtime_include_dirs(_REPO_ROOT)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        "runtime include directory not found. Build the native runtime or install a "
        "wheel that bundles it."
    )


def resolve_transport_library(transport_library: str | Path | None = None) -> Path:
    """Return the static transport library to link against a role model."""

    if transport_library is not None:
        candidate = Path(transport_library)
        if not candidate.is_file():
            raise FileNotFoundError(
                f"transport library does not exist: {candidate}"
            )
        return candidate

    for candidate in native.transport_search_paths(_REPO_ROOT):
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(path) for path in native.transport_search_paths(_REPO_ROOT))
    raise FileNotFoundError(
        "transport library not found (searched: "
        f"{searched}). Build the native transport or install a wheel that bundles it."
    )


def resolve_transport_include(transport_include: str | Path | None = None) -> Path:
    """Return the directory that exposes ``pyfmi_interop/transport/*``."""

    if transport_include is not None:
        candidate = Path(transport_include)
        if not candidate.is_dir():
            raise FileNotFoundError(
                f"transport include directory does not exist: {candidate}"
            )
        return candidate

    for candidate in native.transport_include_dirs(_REPO_ROOT):
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        "transport include directory not found. Build the native transport or "
        "install a wheel that bundles it."
    )


def _model_role(model_dir: Path) -> str:
    """Return the generated model's wire role; missing means ``none``."""

    model_json = model_dir / "model.json"
    if not model_json.is_file():
        return "none"
    try:
        payload = json.loads(model_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none"
    if not isinstance(payload, dict):
        return "none"
    role = payload.get("role")
    return role if isinstance(role, str) and role else "none"


def build_model(
    model_dir: str | Path,
    build_dir: str | Path | None = None,
    *,
    runtime_library: str | Path | None = None,
    runtime_include: str | Path | None = None,
    transport_library: str | Path | None = None,
    transport_include: str | Path | None = None,
    cmake_args: Iterable[str] = (),
) -> Path:
    """Configure and build ``model_dir``; return the built shared library.

    A model whose ``model.json`` carries a wire role other than ``none`` also
    links the static transport archive, so its backends register themselves.
    A ``none`` model keeps the runtime-only link.
    """

    source = Path(model_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"model source directory does not exist: {source}")
    if not (source / "CMakeLists.txt").is_file():
        raise FileNotFoundError(f"no CMakeLists.txt in model source directory: {source}")

    cmake = shutil.which("cmake")
    if cmake is None:
        raise RuntimeError("cmake executable not found on PATH")

    destination = Path(build_dir) if build_dir is not None else source / "build"
    library = resolve_runtime_library(runtime_library)
    include = resolve_runtime_include(runtime_include)
    cmake_module = native.cmake_module_dir(_REPO_ROOT)

    configure = [
        cmake,
        "-S",
        str(source),
        "-B",
        str(destination),
    ]
    if shutil.which("ninja") is not None:
        configure.extend(["-G", "Ninja"])
    configure.extend(
        [
            f"-DPYFMI_INTEROP_RUNTIME_INCLUDE_DIR={include}",
            f"-DPYFMI_INTEROP_RUNTIME_LIBRARY={library}",
            f"-DPYFMI_INTEROP_CMAKE_DIR={cmake_module}",
        ]
    )
    if _model_role(source) != "none":
        configure.extend(
            [
                f"-DPYFMI_INTEROP_TRANSPORT_INCLUDE_DIR="
                f"{resolve_transport_include(transport_include)}",
                f"-DPYFMI_INTEROP_TRANSPORT_LIBRARY="
                f"{resolve_transport_library(transport_library)}",
            ]
        )
    configure.extend(str(argument) for argument in cmake_args)

    _run(configure, "CMake configuration")
    _run([cmake, "--build", str(destination), "-j"], "CMake build")

    return _locate_library(destination, source)


def _locate_library(build_dir: Path, model_dir: Path) -> Path:
    names: list[str] = []
    model_json = model_dir / "model.json"
    if model_json.is_file():
        try:
            payload = json.loads(model_json.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("name"):
                names.append(_shared_library_name(str(payload["name"])))
        except (OSError, ValueError):
            pass

    for name in names:
        for candidate in sorted(build_dir.rglob(name)):
            if candidate.is_file():
                return candidate

    patterns = ["*.so", "*.dylib", "*.dll"]
    for pattern in patterns:
        for candidate in sorted(build_dir.rglob(pattern)):
            if candidate.is_file():
                return candidate

    raise RuntimeError(f"build succeeded but no shared library was found under {build_dir}")


def _shared_library_name(model_name: str) -> str:
    if sys.platform == "win32":
        return f"{model_name}.dll"
    if sys.platform == "darwin":
        return f"lib{model_name}.dylib"
    return f"lib{model_name}.so"


def _run(command: list[str], phase: str) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return
    output = completed.stdout or ""
    raise RuntimeError(
        f"{phase} failed with exit code {completed.returncode}\n"
        f"command: {' '.join(command)}\n"
        f"{output}"
    )
