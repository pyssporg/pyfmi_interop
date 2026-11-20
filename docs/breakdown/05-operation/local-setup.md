---
id: INFO-008
type: info
title: Local setup
summary: Build the native runtime with CMake, install the editable package in a venv, and install the SysML siblings editable from their checkouts.
date: 2026-11-20
status: current
---

# Local setup

Build the native runtime first, then install the Python package in editable
mode inside a venv; the wheel build follows the same order.

- **Toolchain:** Python >= 3.11, CMake, Ninja, and a C++17 compiler.
- **Configure:** `cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release`.
- **Build:** `cmake --build build` produces
  `build/runtime/libpyfmi_interop_runtime.a`.
- **Native tests:** `ctest --test-dir build --output-on-failure`.
- **Install:** `python -m venv .venv`, `. .venv/bin/activate`, then
  `pip install -e ".[dev]"`.
- **Editable vs wheel:** an editable install succeeds without the native
  archives; a wheel build requires them. Building or running a generated model
  needs the archives in `build/runtime/` or the bundled copies under
  `pyfmi_interop/_runtime/`.
- **SysML extra:** `pip install -e ".[sysml]"` where `pycps-sysml2` and
  `pyfmi-sysml2` are available; IR JSON input needs no extra. In the pyssp
  workspace install the siblings editable from their checkouts instead:
  `pip install --no-deps -e ../pycps_sysml2 -e ../pyfmi_sysml2`. Use
  `--no-deps` when the pinned v0.3.0 wheel conflicts; the checkout then
  shadows the release pin.
- **Public API:** the SysML-free path runs through `pyfmi_interop.core`:

  ```python
  from pyfmi_interop.core import ModelSpec, compile_model

  result = compile_model(spec, "build/demo")  # spec: ModelSpec
  print(result.sources, result.library, result.fmu)
  ```

  SysML input parses once, then generates the adapter:
  `parsed = parse(source)`, `generate_adapter(parsed, out, config)`.
- **Wheel:** `python -m build` requires the runtime in `build/runtime/`; a
  source-only install can opt out with `PYFMI_INTEROP_ALLOW_MISSING_RUNTIME=1`.
- **CLI:** the editable install provides `pyfmi-interop`.
