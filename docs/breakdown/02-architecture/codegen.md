---
id: INFO-004
type: info
title: Code generation
summary: core/codegen emits a C++17 source tree and one CMakeLists.txt per model, with typed signals, publish/consume hooks, user_step, and the factory.
date: 2026-11-20
status: current
---

# Code generation

`core/codegen/` turns one `ModelSpec` (or an internal `ModelDefinition`) into a
small C++17 project and one per-model `CMakeLists.txt`.

- **Entry point:** `generate_model(model, out_dir, config)` in
  `core/codegen/__init__.py`; `config` is a `BuildConfig` or `None`. There is no
  `fmi_layer` argument: the SysML boundary chooses the facade.
- **Signals:** typed members, value-reference accessors, initial values, and
  parameter propagation into the model state.
- **Hooks:** publish and consume carry the step frame; `user_step` is the only
  place the model's equations belong.
- **Factory:** the generated unit defines `pyfmi_interop_create_model` and
  its destroy function.
- **Files:** `model_runtime.hpp`, `model_runtime.cpp`, `model_impl.hpp`,
  `bindings.cpp`, a canonical `model.json`, and `CMakeLists.txt`.
- **Runtime link:** the per-model CMake target compiles the two translation
  units and links the static runtime, which carries the checked-in interop FMI
  facade (`src/runtime/src/fmi2_cs_api.cpp`), and its public headers.
- **Determinism:** emission order follows the IR's canonical order; equal input
  produces byte-identical sources.
- **Boundary:** everything is build output except `model_impl.hpp`, the
  designated `user_step` hook; change the IR or a template and regenerate.
- **No model content:** the generator emits the interface and the empty hook; it
  does not synthesize equations or a solver.
