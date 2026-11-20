---
id: INFO-002
type: info
title: Layer and module map
summary: A SysML-free core and a SysML boundary generate, C++ executes, and the generated model joins them through ModelRuntime and one IR.
date: 2026-11-20
status: current
---

# Layer and module map

The Python layer is split into a SysML-free core and a SysML boundary; the
core, the C++ runtime, and the generated model are one-way layers joined by
the IR and the `ModelRuntime` interface.

- **Core (`src/pyfmi_interop/core/`):** SysML-free. `spec.py` (`ModelSpec`,
  `BuildConfig`), `ir.py` (`ModelDefinition`), `timing.py`, `wire/`,
  `serialization/`, `codegen/`, `builder.py`, `packaging.py`, `native.py`,
  `roles.py`, `schema.py`, `pipeline.py` (`compile_model`); it generates,
  builds, and packages without importing SysML.
- **SysML boundary (`src/pyfmi_interop/sysml/`):** `parse.py` (`parse ->
  ParsedModel`, `load_model`, `load_architecture`, `model_from_architecture`),
  `generate.py` (`generate_adapter`), `adapter.py` (the `pyfmi_sysml2` FMI
  layer), and `definitions/` (the bundled `interop.sysml`).
- **One parse:** `parse` loads the architecture once, calls `to_reduction`
  once, and returns `ParsedModel(spec, reduction, unit)`; `generate_adapter`
  consumes that parser-free handle and never reloads the source or re-resolves
  the export unit.
- **Compatibility facades:** `.ir`, `.wire`, `.serialization`, `.codegen`,
  `.builder`, `.packaging`, `.schema`, `.native`, `.roles`, `.timing`,
  `.psysml2`, and `.definitions` keep the old import paths as re-exports only.
- **C++ runtime:** `src/runtime/` holds `ModelRuntime`, the scheduler, the wire
  codec, the `Transport` registry and loopback; `src/transport/` holds UDP/TCP.
- **Wire:** `core/wire/`, `src/runtime/src/wire.cpp`, and
  `core/serialization/` define the envelope, payload schema, and `wire.json`;
  byte transports carry the frame. `core/schema.py` is a backwards-compatible
  facade over the backends.
- **Generated model:** one C++17 source tree per model with typed signals,
  accessors, publish/consume hooks, `user_step`, and the
  `pyfmi_interop_create_model` factory.
- **One FMI facade per artifact:** the core emits the interop facade
  (`fmi2_cs_api.cpp` plus `packaging.render_model_description`); the adapter
  takes its interface, headers, and model description from `pyfmi_sysml2` and
  links the runtime without whole-archive. Both export the same `fmi2*` ABI,
  so they never share a binary.
- **Ingestion:** `sysml/parse.py` loads through `pycps_sysml2` and reduces once
  through `pyfmi_sysml2`; every generator reads the parser-free `Reduction`.
  `PyfmiInterop::*` opts a model into the bundled vocabulary;
  `load_with_interop` adds its roots only for that import. `InteropMetadata` is
  String-only, inherits no `FmuMetadata`, and no generator consumes it, so it
  changes neither `modelDescription.xml` nor the wire.
- **Export selection:** leaf-only among `:> FmuModel` candidates; a shared base
  such as `FmuInterop :> FmuModel` is a role, imported definitions are
  selectable, and a direct FMU is packaged under its bare name.
  `composition=` may name a base; `load_model(includes=...)` and
  `generate --include PATH` pass extra roots to the single load.
- **Packaging and wheel:** `core/packaging.py` writes the FMI XML and the
  deterministic archive; a wheel carries the static runtime and transport
  archives, the public headers under `_runtime/include/`, and
  `_runtime/cmake/wire.cmake`.
