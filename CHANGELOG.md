# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Public `pyfmi_interop.core` contract: `ModelSpec` (the interface),
  `BuildConfig` (serialization, role, prefix), `Compilation`, and
  `compile_model` for generate-build-package in one call. `generate_model`,
  `build_model`, and `package_fmu` are the individual stages.
- SysML-free `examples/core/compile_model.py`, which drives `ModelSpec`
  through `compile_model` without the `sysml` extra.
- Reusable `PyfmiInterop` SysML library shipped as package data: a model can
  `import PyfmiInterop::*` to get the `FmuInterop :> FmuModel` base, its
  `InteropDeployment` initialization parameters, and `InteropMetadata`.
- `interop_definitions()` returns the bundled library path, and both
  `load_model` and the `psysml2` generation path include it automatically.
- Multi-package SysML includes: `load_model(includes=...)`,
  `generate_model(sysml_includes=...)`, and repeatable
  `generate --include PATH` pass extra package roots to the IR load and the
  `psysml2` reparse.
- Library-defined FMUs are export units: a leaf an included package declares
  can be selected, and a direct FMU is packaged under its bare name.
- Multi-unit example `examples/system/`: `build_one.py` packages one selected
  `FmuInterop` unit and `build_all.py` packages every unit `fmu_units()`
  enumerates, one FMU each.
- `load_architecture(source, includes=...)` returns the loaded `Architecture`,
  and `load_model(..., composition=...)` / `model_from_architecture(...,
  composition=...)` reduce one named unit. The CLI has no such selector.

### Changed

- The Python layer is split into a SysML-free `core/` and a `sysml/` boundary.
  `core/` holds `spec`, the IR, timing, wire, serialization, codegen, builder,
  packaging, and `compile_model`; `sysml/` holds `parse`, `generate_adapter`,
  the `pyfmi_sysml2` adapter layer, and the bundled definitions. The old import
  paths (`pyfmi_interop.ir`, `.wire`, `.serialization`, `.codegen`, `.builder`,
  `.packaging`, `.schema`, `.native`, `.roles`, `.timing`, `.psysml2`,
  `.definitions`) remain as re-export-only compatibility facades.
- SysML is parsed once: `parse` returns `ParsedModel(spec, architecture, unit,
  composition)`, and `generate_adapter` consumes that handle instead of
  reloading the source.
- One FMI facade per artifact: the core emits the interop facade, and the
  adapter takes its FMI interface, headers, and model description from
  `pyfmi_sysml2`. Both export the same `fmi2*` ABI but never share a binary;
  `generate_model` no longer takes `fmi_layer`.
- Examples move to `examples/core/` and `examples/sysml/{adapter,system}/`.
  Tests split into `tests/core/` and the `sysml`-marked `tests/sysml/`; the
  default gate is `pytest -m "not sysml"`.
- The adapter example inherits the shared `FmuInterop` base and
  `InteropDeployment` port instead of declaring them locally; it is now a
  direct FMU (`modelName="ActuatorLink"`).
- Native sources live under `src/`: `runtime/` is `src/runtime/`, `transport/`
  is `src/transport/`, and the vendored FMI headers are `3rd_party/fmi2/`
  instead of `third_party/`. CMake, `setup.py`, the sdist manifest, and the
  Python path resolution follow the new layout.

### Fixed

- The invalid `Topic :: Scientific/Engineering :: Simulation` classifier no
  longer blocks metadata generation; the valid parent classifier is used.

## [0.5.0] - 2026-11-20

### Breaking

- `model_id` uses the `pyfmi_interop.model-id.v2` hash domain: the digest is the
  model name plus the wire signals ordered by `(value_reference, name)`, with no
  step size and no parameters. Timing and deployment configuration no longer
  move the identity, and peers built against v1 identities must be rebuilt.

### Added

- Adapter generation on the `pyfmi_sysml2` FMI layer: `generate_model` accepts
  `fmi_layer="psysml2"` with `sysml_source=`, and the new
  `pyfmi_interop.psysml2` module takes the FMI 2.0 C interface, headers, and
  `modelDescription.xml` from the shared SysML-to-FMI generator while this
  repository supplies the five model hooks and owns the wire plane. The
  default `interop` layer still renders its own facade.
- Deployment parameters as FMI variables (`causality="parameter"`,
  `variability="fixed"`) with authored defaults, bound by the master before
  `fmi2EnterInitializationMode`; the transport is opened there from
  `transport`, `bind_address`, `peer_address`, `queue_depth`, and `deadline_s`,
  per instance. An unknown transport value fails initialization with the
  accepted values, a write after initialization is rejected, and the
  `PYFMI_INTEROP_TRANSPORT*` environment variables remain only as a fallback
  for a model that declares no parameter interface.
- `package_fmu` accepts `model_description`, `model_json`, `model_name`,
  `extra_entries`, and `include_schema`, so an external FMI generator can inject
  its document and schemas while the packager still fixes archive layout,
  timestamps, and order.
- `Serialization` backends may supply their own payload identity
  (`payload_message`, `proto_package`), an external proto tree, and the CMake
  additions their target needs (`cmake_proto_sources`,
  `cmake_proto_import_roots`, `cmake_include_dirs`, `cmake_link_libraries`).
  Codegen accepts any registered backend name; `packed` and `protobuf` still
  generate byte-identical output.

### Changed

- FMI value references and wire field numbers are separate namespaces: FMI
  value references are zero-based in declaration order, parameters included,
  while wire fields are `1..n` over inputs and outputs in canonical signal-name
  order. Adding a parameter no longer renumbers the wire.
- Adapters are step-free: `ModelDefinition.step_size_s` is optional and an
  adapter validates its declared rates against the slowest one. Step size
  leaves the wire identity, the model description (`DefaultExperiment` is
  emitted only for realtime models), and the build inputs; parameters change
  from `variability="tunable"` to `"fixed"`.
- Timing and transport metadata are ordinary typed attributes; the retired
  `pyssp_*` control spelling is no longer read. On a port definition the
  attribute must be typed by a dialect container marker such as an
  `attribute def` specializing `ParameterSet` so the FMI reduction skips it,
  while on a part definition any resolved `attribute def` suffices.
- `pycps-sysml2` and `pyfmi-sysml2` in the `sysml` extra pin the v0.3.0 wheels.
- Canonical wire order is now stated as signal-name order: ports may be
  reordered in SysML without renumbering the wire, and an SSP connector binds
  variable names, not value references. The assignment already sorted by name;
  the architecture and intent text said `component_interface` order.

### Fixed

- `pyfmi_interop_wire_add_proto` compiled an imported proto at its basename, so
  a proto under a nested directory emitted headers at the wrong path, and the
  consumer target carried no compile-order edge to protoc. An external proto
  tree now builds in one cold pass.

## [0.4.0] - 2026-11-19

### Added

- Serialization registry with `protobuf` (canonical), `packed` (deterministic
  little-endian, no third-party dependency, generated C++ codec), and `opaque`
  (format id 0, passthrough) backends; `generate --serialization` and the `serializations`
  CLI verb; only the selected backend's schema artifacts are bundled, and
  `resources/transport.json` documents the default transport and endpoint keys.
- Part-definition message naming with collision-checked identifier
  sanitization (`out.value[0]` -> `out_value_0`), one scalar field per array
  element, per-field `wire` direction metadata (inverse of FMI causality), and
  `format`/`format_id` in `wire.json`.
- Generated `publish`/`consume` now copy real signal values in the wire
  direction instead of only carrying the step time, and the interface role
  (`sender`/`receiver`/`adapter`/`none`) is derived and exposed in
  `model.json`/`wire.json`, with a narrowing-only `--role` override.
- Wire version 2: 56-byte header with an explicit `payload_format` tag,
  zero-required flags/reserved fields, and distinct decode errors for both.

## [0.3.0] - 2026-11-19

First wire-only release. This is a breaking release: everything that bound the
model interface to a protocol is gone, and the wire envelope is the only
contract.

### Breaking

- Remove the adapter catalogue, `TransportBinding`/`bindings`, and adapter
  names; `pyfmi-interop` no longer accepts an adapter. Model JSON that still
  carries `bindings` loads and ignores the field.
- Remove `third_party/{OpenRTI,DCPLib,ED247_LIBRARY}` and the protocol-submodule
  build integration that depended on them: the HLA, DCP, ED-247, DIS, and ROS 2
  adapter stubs, `AdapterDependency`, `vcpkg_features()`, `adapter_manifest()`,
  and the `adapters` CLI verb. Transport, medium, and discovery belong outside
  this repository.
- The unreleased adapter and submodule work from the pre-0.3.0 line is removed
  before this release; it never shipped.

### Added

- Versioned 48-byte wire envelope (`pyfmi_interop.wire`): little-endian magic
  (`PFMI`), wire version, header size, derived 8-byte model id, instance,
  sequence, nanosecond timestamp, payload length, payload CRC32, and header
  CRC32 around an opaque protobuf payload. `encode`/`decode`/`model_id` with a
  typed `WireError` taxonomy, the exact byte layout, and golden frames in
  `docs/wire.md`.
- Deterministic model-id derivation: the first 8 bytes of SHA-256 over the
  domain separator, the model name, the step size, and the signal records
  ordered by `(value_reference, name)`; the C++ end reproduces the Python
  vectors.
- Schema bundle shipped inside every packaged FMU: `<Model>.proto` (proto3,
  payload fields numbered by IR `value_reference`) and `wire.json` (format
  version, model id, step size, signals, rate groups), both deterministic and
  emitted next to the binary. The `schema` CLI verb writes the bundle from a
  `model.json`; `ProjectionError` fails packaging instead of dropping a signal.
- C++ end of the wire envelope in `runtime/src/wire.cpp`: packed little-endian
  header, CRC32/ISO-HDLC, and a portable SHA-256 model id that matches the
  Python vectors. `encode_frame`/`decode_frame` return typed `ErrorCode`
  failures mirroring the Python `WireError` taxonomy.
- `PYFMI_INTEROP_WIRE` string option (`protobuf` or `raw`) in
  `cmake/wire.cmake`, exposed as the `PYFMI_INTEROP_WIRE_MODE` cache variable,
  target property, and compile definition. It defaults to `protobuf` when
  libprotobuf and `protoc` are found, otherwise `raw`.
- Generated models emit `<Model>.proto`, `wire.json`, and `model_wire.cpp`. In
  `protobuf` mode the project compiles its schema with `protoc`, maps signal
  values to and from `<Model>Payload` through the protobuf reflection API, and
  builds a `wire_conformance` executable whose frames are byte-identical to
  Python `wire.encode`.
- CLI `transports` verb listing the byte transport names, plus Python/C++
  conformance tests that cover the golden frames, round-trip, CRC, version,
  truncation, trailing-byte failures, and frame byte identity in both wire
  modes.
- IR field-id contract: value references are wire field ids assigned once and
  append-only (`0` reserved); `DataType` and `Direction` keep stable JSON
  strings with frozen protobuf enum numbers (`0` = wire unspecified); string
  signals carry a positive capacity; `unit is None` means unspecified and
  `unit == ""` means dimensionless.

### Changed

- The wheel is a platform wheel carrying the prebuilt static runtime; the
  native runtime must be built before `python -m build`.

## [0.2.0] - 2026-11-19

### Changed

- Renamed the project from `pyfmi-distributed` to `pyfmi-interop`: the Python
  module is now `pyfmi_interop`, the C++ namespace and include directory are
  `pyfmi_interop`, the CLI is `pyfmi-interop`, and CMake targets and options are
  `pyfmi_interop_*` and `PYFMI_INTEROP_*`.

### Breaking

- Environment variables `PYFMI_DIST_*` are now `PYFMI_INTEROP_*`; there are no
  compatibility aliases or fallbacks.
- The C ABI factory is now `pyfmi_interop_create_model` /
  `pyfmi_interop_destroy_model`.
- C++ includes move from `pyfmi_distributed/runtime/...` to
  `pyfmi_interop/runtime/...`.
- The `pyfmi_distributed` Python module and the `pyfmi-distributed`
  distribution/CLI names are removed without shims.
