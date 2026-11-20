---
id: INFO-008
type: info
title: Local setup
summary: Build the native runtime with CMake, then install the editable Python package with the dev extra.
date: 2026-11-09
status: current
---

# Local setup

Build the native runtime first, then install the Python package in editable
mode; the wheel build follows the same order.

- **Toolchain:** Python >= 3.11, CMake, Ninja, and a C++17 compiler.
- **Configure:** `cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release`.
- **Build:** `cmake --build build` produces
  `build/runtime/libpyfmi_interop_runtime.a`.
- **Native tests:** `ctest --test-dir build --output-on-failure`.
- **Install:** `python -m venv .venv`, activate it, then
  `pip install -e ".[dev]"`.
- **Editable vs wheel:** an editable install succeeds without the native
  archives; a wheel build requires them. Building or running a generated model
  needs the archives in `build/runtime/` or the bundled copies under
  `pyfmi_interop/_runtime/`.
- **SysML extra:** `pip install -e ".[sysml]"` where `pycps-sysml2` and
  `pyfmi-sysml2` are available; IR JSON input needs no extra.
- **Wheel:** `python -m build` requires the runtime in `build/runtime/`; a
  source-only install can opt out with `PYFMI_INTEROP_ALLOW_MISSING_RUNTIME=1`.
- **CLI:** the editable install provides `pyfmi-interop`.
