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

- **Python:** `ir.py`, `sysml.py`, `definitions/`, `timing.py`, `codegen/`,
  `builder.py`, `packaging.py`, and `cli.py`.
- **C++ runtime:** `src/runtime/` holds `ModelRuntime`, the fixed-step
  scheduler, the wire codec, the `Transport` registry, and the loopback
  backend; `src/transport/` holds the UDP and TCP backends.
- **Wire:** `src/pyfmi_interop/wire/`, `src/runtime/src/wire.cpp`,
  `src/pyfmi_interop/serialization/protobuf.py`, and
  `src/pyfmi_interop/serialization/descriptor.py`
  define the envelope and payload schema; byte transports carry the frame.
  `schema.py` is a backwards-compatible facade over the serialization backends.
- **Generated model:** one C++17 source tree per model with typed signals,
  accessors, publish/consume hooks, `user_step`, and
  `pyfmi_interop_create_model`.
- **Flow:** SysML or IR JSON to IR, to generated C++ and CMake, to a native
  build, to an FMI 2.0 CoSimulation `.fmu`.
- **Ingestion:** `sysml.py` uses `pycps_sysml2` and `pyfmi_sysml2`; the IR stays
  independent of both and of FMI. A model opts into the bundled `PyfmiInterop`
  vocabulary with `private import PyfmiInterop::*;`;
  `interop_definitions()` returns the library path, and
  `load_with_interop` adds it to the load roots only for that declaration.
  `InteropMetadata` is String-only, does not inherit `FmuMetadata`, and no
  generator consumes it yet, so it does not change `modelDescription.xml` or
  the wire.
- **Export selection:** leaf-only among `:> FmuModel` candidates. A shared base
  such as `FmuInterop :> FmuModel` is a role, while imported definitions are
  selectable: a library-defined leaf is the export unit and a direct FMU is
  packaged under its bare name. `composition=` may name a base explicitly.
- **Multi-package loads:** `load_model(includes=...)` and
  `generate --include PATH` pass the same extra package roots to the IR load
  and the `psysml2` reparse, so an app file that only imports a library resolves
  the library's definitions and exports its leaf.
- **Packaging:** `packaging.py` reads the IR for names and value references and
  writes the FMI XML plus the deterministic archive.
- **Wheel:** a platform wheel carries the static runtime and transport archives,
  the runtime and transport public headers under `_runtime/include/`, and
  `_runtime/cmake/wire.cmake`; no source checkout is needed to link a generated
  model.
