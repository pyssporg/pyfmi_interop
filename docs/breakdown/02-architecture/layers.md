---
id: INFO-002
type: info
title: Layer and module map
summary: A SysML-free core generates from an interface specification, C++ executes, and the generated model joins them through ModelRuntime and one IR; SysML composition lives in pyfmi_sysml.
date: 2026-11-22
status: current
---

# Layer and module map

The Python layer in this repository is SysML-free; the core, the C++ runtime,
and the generated model are one-way layers joined by the IR and the
`ModelRuntime` interface. SysML ingestion is a separate composition layer, not a
package in this tree.

- **Core (`src/pyfmi_interop/core/`):** SysML-free. `spec.py` (`ModelSpec`, `BuildConfig`), `ir.py` (`ModelDefinition`), `timing.py`, `wire/`,
  `serialization/`, `codegen/`, `builder.py`, `packaging.py`, `native.py`,
  `roles.py`, `schema.py`, `pipeline.py` (`compile_model`), and `adapter.py`
  (the adapter model and its `pyfmi_interfaces` FMI layer); it takes IR JSON
  or a `ModelSpec` and generates, builds, and packages without importing SysML.
- **Composition boundary (`pyfmi_sysml`, separate repository):** `parse` loads
  through `pycps_sysml2`, reduces once, maps to `ModelSpec`, and
  `generate_adapter` calls `core.adapter.adapter_from_reduction`; interop never loads the source or re-resolves the export unit.
- **Interface model (`pyfmi_interfaces`, renamed from `pyfmi_sysml2`):** owns
  the FMI interface model and emitters; the adapter and the composition layer
  consume it. It is SysML-free.
- **Vocabulary (`pyssp_sysml_definitions`, separate repository):** carries
  `PysspCore` and the artifact vocabularies (`PyfmiInterop`, later FMI/SoS),
  installs with no Python dependencies, while `pycps_sysml2` depends on it and
  keeps the parser, IR, and policies.
- **Compatibility facades:** `.ir`, `.wire`, `.serialization`, `.codegen`,
  `.builder`, `.packaging`, `.schema`, `.native`, `.roles`, and `.timing` keep
  the old import paths as re-exports only.
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
  takes its interface, headers, and model description from `pyfmi_interfaces`
  and links the runtime without whole-archive. Both export the same `fmi2*`
  ABI, so they never share a binary.
- **CLI ingress:** `generate` accepts IR JSON; the Python API takes IR or a
  `ModelSpec`. There is no `--sysml` flag or `[sysml]` extra; SysML enters at
  `pyfmi-sysml`.
- **Export selection (`pyfmi_sysml`):** leaf-only among `:> FmuModel`
  candidates; a shared base such as `FmuInterop :> FmuModel` is a role,
  imported definitions are selectable, and a direct FMU is packaged under its
  bare name. `composition=` may name a base; `includes=` passes extra roots to
  the single load.
- **Packaging and wheel:** `core/packaging.py` writes the FMI XML and the
  deterministic archive; a wheel carries the static runtime and transport
  archives, the public headers under `_runtime/include/`, and
  `_runtime/cmake/wire.cmake`.
