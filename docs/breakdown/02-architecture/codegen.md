---
id: INFO-004
type: info
title: Code generation
summary: codegen emits a C++17 source tree and one CMakeLists.txt per model, with typed signals, binding hooks, user_step, and the factory.
date: 2026-11-09
status: current
---

# Code generation

`codegen/` turns one `ModelDefinition` into a small C++17 project and one
per-model `CMakeLists.txt`.

- **Signals:** typed members, value-reference accessors, initial values, and
  parameter propagation into the model state.
- **Hooks:** publish and consume call the bound adapter; `user_step` is the only
  place the model's equations belong.
- **Factory:** the generated unit defines `pyfmi_interop_create_model` and
  its destroy function.
- **Files:** `model_runtime.hpp`, `model_runtime.cpp`, `model_impl.hpp`,
  `bindings.cpp`, a canonical `model.json`, and `CMakeLists.txt`.
- **Runtime link:** the per-model CMake target compiles the two translation
  units and links the static runtime and its public headers.
- **Determinism:** emission order follows the IR's canonical order; equal input
  produces byte-identical sources.
- **Boundary:** everything is build output except `model_impl.hpp`, the
  designated `user_step` hook; change the IR or a template and regenerate.
- **No model content:** the generator emits the interface and the empty hook; it
  does not synthesize equations or a solver.
