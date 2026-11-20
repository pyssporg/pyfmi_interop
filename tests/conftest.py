"""Shared helpers for the core and SysML test suites.

Only helpers live here: no tests, and no fixture that changes what a test
asserts.  The demo model is the five-signal fixture the golden artifacts were
generated from.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from pyfmi_interop import native
from pyfmi_interop.core import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
)
from pyfmi_interop.core.ir import deterministic_guid

REPO_ROOT = Path(__file__).resolve().parents[1]

_CMAKE = shutil.which("cmake")
_CXX = (
    shutil.which(os.environ.get("CXX", "c++"))
    or shutil.which("g++")
    or shutil.which("clang++")
)


def skip_reason(posix_message: str = "the end-to-end runner is POSIX-only") -> str | None:
    """Return why a native end-to-end test cannot run, or ``None``."""

    if _CMAKE is None:
        return "cmake is not available"
    if _CXX is None:
        return "a C++ compiler is not available"
    if sys.platform == "win32":
        return posix_message
    if not native.bundled_library_path().is_file() and not native.default_runtime_library_path(
        REPO_ROOT
    ).is_file():
        return "the native runtime has not been built"
    if not native.bundled_transport_library_path().is_file() and not any(
        path.is_file() for path in native.transport_search_paths(REPO_ROOT)
    ):
        return "the native transport has not been built"
    return None


def free_udp_port() -> int:
    """Bind an ephemeral UDP port, then release it for the runner."""

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def compile_runner(
    directory: Path,
    library: Path,
    source_text: str,
    *,
    stem: str = "runner",
) -> Path:
    """Compile ``source_text`` against a generated model and return the binary."""

    source = directory / f"{stem}.cpp"
    source.write_text(source_text, encoding="utf-8")
    executable = directory / stem
    headers = REPO_ROOT / "3rd_party" / "fmi2" / "headers"
    completed = subprocess.run(
        [
            _CXX or "c++",
            "-std=c++17",
            "-O0",
            str(source),
            str(library),
            "-I",
            str(headers),
            f"-Wl,-rpath,{library.parent}",
            "-pthread",
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return executable


@pytest.fixture
def demo_model() -> ModelDefinition:
    """The five-signal model the golden artifacts were generated from."""

    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s", initial=1.5),
        Signal("setpoint", 5, DataType.REAL, Direction.INPUT, rate_hz=50.0),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        rate_groups=(RateGroup("fast", 0.02, 0.01, ("setpoint",)),),
        description="codegen fixture",
    )
