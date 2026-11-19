from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # pragma: no cover - wheel is a build dependency
    _bdist_wheel = None


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pyfmi_interop.native import (  # noqa: E402
    default_runtime_library_path,
    runtime_library_name,
    transport_library_name,
    transport_search_paths,
)


class build_py(_build_py):
    """Bundle the native runtime and its headers into the wheel."""

    def run(self) -> None:
        super().run()
        self._bundle_runtime()

    def _bundle_runtime(self) -> None:
        source = default_runtime_library_path(ROOT)
        if not source.is_file():
            # An editable install is used while developing; the runtime is built
            # separately and found through native.runtime_search_paths().  A
            # wheel, however, must never ship without the native archive.
            if getattr(self, "editable_mode", False) or os.environ.get(
                "PYFMI_INTEROP_ALLOW_MISSING_RUNTIME"
            ) == "1":
                return
            raise FileNotFoundError(
                f"native runtime not found: {source}. "
                "Run 'cmake -S . -B build && cmake --build build' before "
                "building the wheel, or set PYFMI_INTEROP_ALLOW_MISSING_RUNTIME=1 "
                "for a source-only install."
            )

        transport_source = next(
            (
                candidate
                for candidate in transport_search_paths(ROOT)
                if candidate.is_file()
            ),
            None,
        )
        if transport_source is None:
            # Same policy as the runtime: an editable develop install may find
            # the archive in the source tree, but a wheel must ship it.
            if not (
                getattr(self, "editable_mode", False)
                or os.environ.get("PYFMI_INTEROP_ALLOW_MISSING_RUNTIME") == "1"
            ):
                raise FileNotFoundError(
                    "native transport library not found. Run "
                    "'cmake -S . -B build && cmake --build build' before "
                    "building the wheel, or set "
                    "PYFMI_INTEROP_ALLOW_MISSING_RUNTIME=1 for a source-only install."
                )

        destination_dir = Path(self.build_lib) / "pyfmi_interop" / "_runtime"
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination_dir / runtime_library_name())
        if transport_source is not None:
            shutil.copy2(
                transport_source, destination_dir / transport_library_name()
            )

        headers_source = ROOT / "runtime" / "include"
        headers_target = destination_dir / "include"
        if headers_target.exists():
            shutil.rmtree(headers_target)
        shutil.copytree(headers_source, headers_target)
        # Both headers share the pyfmi_interop/ root, so merge rather than
        # replace the runtime headers.
        shutil.copytree(
            ROOT / "transport" / "include", headers_target, dirs_exist_ok=True
        )

        cmake_target_dir = destination_dir / "cmake"
        cmake_target_dir.mkdir(parents=True, exist_ok=True)
        cmake_source = ROOT / "cmake" / "wire.cmake"
        if not cmake_source.is_file():
            raise FileNotFoundError(f"CMake module not found: {cmake_source}")
        shutil.copy2(cmake_source, cmake_target_dir / "wire.cmake")


if _bdist_wheel is not None:

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self) -> None:
            super().finalize_options()
            self.root_is_pure = False

        def get_tag(self) -> tuple[str, str, str]:
            _, _, platform_tag = super().get_tag()
            return "py3", "none", platform_tag


cmdclass = {"build_py": build_py}
if _bdist_wheel is not None:
    cmdclass["bdist_wheel"] = bdist_wheel


setup(cmdclass=cmdclass)
