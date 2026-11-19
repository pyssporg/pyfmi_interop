---
id: INFO-002
type: info
title: Layer and module map
summary: Python generates, C++ executes, and the generated model joins them through the ModelRuntime interface and one IR.
date: 2026-11-09
status: current
---

# Layer and module map

The Python generation layer, the C++ runtime, and the generated model are
separate, one-way layers joined by the IR and the `ModelRuntime` interface.

- **Python:** `ir.py`, `sysml.py`, `timing.py`, `codegen/`, `builder.py`,
  `packaging.py`, and `cli.py`.
- **C++ runtime:** `runtime/` holds `ModelRuntime`, the fixed-step scheduler, and
  the `Transport` registry; protocol mapping code is under
  `runtime/src/adapters/`.
- **Dependencies:** `cmake/adapters.cmake` and `vcpkg.json` acquire the prebuilt
  upstream protocol libraries from an installed package, a `third_party/<lib>`
  submodule, or FetchContent; the repository does not reimplement protocol
  serialization.
- **Generated model:** one C++17 source tree per model with typed signals,
  accessors, binding hooks, `user_step`, and `pyfmi_interop_create_model`.
- **Flow:** SysML or IR JSON to IR, to generated C++ and CMake, to a native
  build, to an FMI 2.0 CoSimulation `.fmu`.
- **Ingestion:** `sysml.py` uses `pycps_sysml2` and `pyfmi_sysml2`; the IR stays
  independent of both and of FMI.
- **Packaging:** `packaging.py` reads the IR for names and value references and
  writes the FMI XML plus the deterministic archive.
- **Wheel:** a platform wheel carries the static runtime and public headers
  under `_runtime/`; no source checkout is needed to link a generated model.
