---
id: INFO-002
type: info
title: Layer and module map
summary: A SysML-free core generates from an interface specification, C++ executes, and the generated model joins them through ModelRuntime and one IR; SysML composition lives in pyfmi_sysml.
date: 2026-11-22
status: current
---

# Layer and module map

The Python layer is SysML-free; core, C++ runtime, and generated model are
one-way layers joined by the IR and `ModelRuntime`. SysML ingestion is a
separate composition layer, not a package in this tree.

- **Core (`src/pyfmi_interop/core/`):** SysML-free: `spec.py`, `ir.py`, `timing.py`,
  `attributes.py` (`INFO-011`), `wire/`, `serialization/`, `codegen/`, `builder.py`,
  `packaging.py`, `native.py`, `roles.py`, `schema.py`, `pipeline.py`, and `adapter.py`,
  the public facade over `adapter_model.py` and `adapter_render.py`.
- **Adapter API:** `adapter_from_reduction`, `select_component` (delegating to
  `pyfmi_interfaces.core.select_component`), `require_fmi_layer`, and
  `write_adapter_tree` (whole tree, model description without `DefaultExperiment`);
  no private re-exports.
- **Composition boundary (`pyfmi_sysml`):** `parse` loads through `pycps_sysml2`,
  reduces once, extracts plain attribute values, and maps to `ModelSpec`;
  `generate_adapter` calls the two public adapter names. Interop never loads the
  source or re-resolves the export unit.
- **Interface model (`pyfmi_interfaces`, renamed from `pyfmi_sysml2`):** owns the
  FMI interface model and emitters, and is SysML-free.
- **Vocabulary (`pyssp_sysml_definitions`):** carries `PysspCore` and the artifact
  vocabularies (`PyfmiInterop`, later FMI/SoS) with no Python dependencies;
  `pycps_sysml2` depends on it and keeps the parser, IR, and policies.
- **Compatibility facades:** `.ir`, `.wire`, `.serialization`, `.codegen`,
  `.builder`, `.packaging`, `.schema`, `.native`, `.roles`, and `.timing` re-export.
- **C++ runtime:** `src/runtime/` holds `ModelRuntime`, the scheduler, the wire
  codec, the `Transport` registry and loopback; `src/transport/` holds UDP/TCP.
- **Wire:** `core/wire/`, `src/runtime/src/wire.cpp`, and `core/serialization/`
  define the envelope, payload schema, and `wire.json`; byte transports carry
  the frame. `core/schema.py` is a backwards-compatible facade over the backends.
- **Generated model:** one C++17 source tree per model with typed signals,
  accessors, publish/consume hooks, `user_step`, and the
  `pyfmi_interop_create_model` factory.
- **One FMI facade per artifact:** the core emits the interop facade
  (`fmi2_cs_api.cpp` plus `packaging.render_model_description`); the adapter
  takes its interface, headers, and model description from `pyfmi_interfaces`
  and links the runtime without whole-archive; they never share a binary.
- **CLI ingress:** `generate` accepts IR JSON; the Python API takes IR or a
  `ModelSpec`. There is no `--sysml` flag or `[sysml]` extra; SysML enters at
  `pyfmi-sysml`.
- **Export selection (`pyfmi_sysml`):** leaf-only among `:> FmuModel` candidates;
  a shared base such as `FmuInterop :> FmuModel` is a role, imported definitions
  are selectable, and a direct FMU is packaged under its bare name.
  `composition=` may name a base; `includes=` passes extra roots to the single load.
- **Packaging and wheel:** `core/packaging.py` writes the FMI XML and the
  deterministic archive; a wheel carries the static runtime and transport
  archives, public headers under `_runtime/include/`, and `_runtime/cmake/wire.cmake`.
