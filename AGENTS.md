# AGENTS

## Vision first (required)

Before you read code, edit files, or plan a change, read the project vision:

**`docs/breakdown/00-intent/intent.md`**

It states why this repository exists, what it commits to, and what it refuses to
become. It is the first document to read, not a reference of last resort.

- Read it in full before making any change to code, tests, docs, or artifacts.
- Judge every proposed change against it. If a change conflicts with the vision,
  its commitments, goals, or non-goals, stop and surface the conflict; do not
  implement it silently.
- If the work shows the long-term direction is wrong, change the vision
  deliberately first, then the code. Never let the repository drift away from
  its stated intent.

## Rules

1. **Don't assume. Surface tradeoffs.** If a contract is ambiguous, stop and say
   so rather than picking a behaviour silently.
2. **Minimum code that solves the problem.** Nothing speculative.
3. **Touch only what you must.** Clean up only your own mess.
4. **Define success criteria and verify.**

## Repository Focus

`pyfmi_interop` turns a SysML v2 definition of an FMU into an optimized
C++17 realtime runtime plus transport adapters, and packages the result as an
FMI 2.0 CoSimulation FMU.

- The Python layer ingests SysML or IR JSON, emits C++ and CMake, builds the
  native model, and packages the FMU.
- The C++ layer in `runtime/` owns the reusable `ModelRuntime` interface, the
  fixed-step scheduler, and the `Transport` registry.
- The generated model owns the typed signal members, value-reference
  accessors, binding hooks, the `user_step` hook, and the factory
  `pyfmi_interop_create_model`.
- Current state, contracts, and design rationale live in `docs/breakdown/`; the
  code is the source of truth only after the owning leaf has been updated.

## Hard constraints

- **One IR.** `src/pyfmi_interop/ir.py` is the only signal, rate, and
  binding model. Every generator, the builder, and the packager read it; none
  re-derives value references or timing.
- **One adapter catalogue.** `src/pyfmi_interop/adapters.py` is the only
  adapter list. The CLI, CMake options, and documentation read the same table;
  no protocol-specific branch grows elsewhere.
- **The generated artifact is the unit under test.** Assertions run against the
  emitted C++ source, the per-model CMake build, or the packed `.fmu`, not
  against an intermediate string the writer might not use.
- **Deterministic output.** Equal IR and equal inputs produce byte-identical
  generated sources, FMI XML, and `.fmu` archives. The GUID is the stable uuid5
  from the model name; timestamps and zip order are fixed by packaging.
- **No external protocol library is a hard build dependency.** HLA, DIS, DCP,
  ROS 2, and ED-247 are compile-gated stubs behind `PYFMI_INTEROP_ENABLE_*`,
  default OFF. A stub reports unavailable; it never silently substitutes
  another transport.
- **Protocol libraries are prebuilt, never reimplemented.** Each adapter binds
  an upstream library through its public API; protocol-specific mapping code
  lives in `runtime/src/adapters/`. The build acquires the library from an
  installed package (vcpkg or system) first, then a `third_party/<lib>`
  submodule, then FetchContent when `-DPYFMI_INTEROP_ALLOW_FETCH=ON`, and otherwise
  fails with the upstream URL and pin. ROS 2 is consumed from a system Jazzy
  installation only and must never be vendored. DCP is ASAM X-DCP via DCPLib,
  not DDS.
- **Do not edit generated files by hand.** Change the IR, the generator, or the
  template, then regenerate. A hand edit is overwritten and hides the real
  source of the change. The one exception is `model_impl.hpp`, the designated
  `user_step` hook where model equations belong.
- **No model equations, no master algorithm.** SysML defines the interface, not
  the equations; `user_step` is the only place model behaviour is written, and
  the runtime is a slave, not a co-simulation master.

## Conventions

- `README.md` is the landing page for users; `AGENTS.md` is for contributors.
- Current state lives in `docs/breakdown/` leaves, in the present tense. Dated
  decisions live in `docs/archive/archive.zip`, read with `pb archive`; never
  add per-layer `decisions/` folders.
- Regenerate `docs/archive/README.md`, `design-choice-log.md`, and
  `traceability-map.md` with `pb registers`; never edit generated registers by
  hand.
- Keep docs aligned with the actual CLI, file layout, and dependency pins.
- Preserve user changes in a dirty worktree; never revert unrelated edits.

## Environment

- Python >= 3.10 and a C++17 compiler; `cmake` and `ninja` build the native
  runtime.
- Native build: `cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release` then
  `cmake --build build`.
- Native tests: `ctest --test-dir build --output-on-failure`.
- Install: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
- SysML ingestion: `pip install -e ".[sysml]"` in a workspace that provides
  `pycps-sysml2` and `pyfmi-sysml2`.
- Tests: `python -m pytest -m "not slow"`; the default CI gate. Full suite:
  `python -m pytest`.
- Lint: `ruff check src tests`.
- Breakdown checks: `python3 <pb> check --strict --root docs/breakdown` and
  `python3 <pb> node-size --strict --root docs/breakdown`, where `<pb>` is the
  product-breakdown skill's `scripts/pb`.
