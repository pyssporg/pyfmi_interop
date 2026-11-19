# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [Unreleased]

### Breaking

- Breaking: remove the adapter catalogue and protocol submodules; adapter names
  are no longer accepted.

### Added

- Git repository with pinned protocol submodules: OpenRTI (HLA, `fb454e6`),
  DCPLib (ASAM X-DCP, `v0.2`), and Airbus ED247_LIBRARY (`VA2.3.0`).
- Build-only integration workarounds for OpenRTI's top-level CMake assumptions
  and ED247_LIBRARY's missing `<limits>` include; the submodules stay pristine.
- Python IR with typed signals, value references, rate groups, and transport
  bindings.
- SysML v2 ingestion through `pycps_sysml2` and `pyfmi_sysml2`, plus JSON IR
  loading.
- C++17 code generation for a typed model runtime, binding hooks, the
  `user_step` hook, and the `pyfmi_distributed_create_model` factory.
- Static runtime with the `ModelRuntime` interface, a fixed-step realtime
  scheduler, and the `Transport` registry.
- Loopback adapter, always built.
- Compile-gated HLA, DIS, DCP, ROS 2, and ED-247 adapter stubs behind
  `PYFMI_DIST_ENABLE_*`, default OFF.
- CMake model build and deterministic FMI 2.0 CoSimulation packaging.
- `pyfmi-distributed` CLI with `adapters`, `inspect`, `generate`, `build`, and
  `package`.
- Product breakdown, architecture, adapter, and usage documentation.
- Example 1 kHz loopback model in `examples/loopback/model.json`.
- Adapter dependency metadata (`AdapterDependency`) plus `vcpkg_features()` and
  `adapter_manifest()`, with a `vcpkg.json` feature manifest and
  `cmake/adapters.cmake` acquisition layer.
- Dependency acquisition order: installed package (vcpkg/system), then
  `third_party/<lib>` submodule, then FetchContent with
  `-DPYFMI_DIST_ALLOW_FETCH=ON`, then a hard error naming the upstream URL.
- Versioned 48-byte wire envelope (`pyfmi_interop.wire`): little-endian magic,
  wire version, header size, derived 8-byte model id, instance, sequence,
  nanosecond timestamp, payload length, payload CRC32, and header CRC32 around
  an opaque protobuf payload. `encode`/`decode`/`model_id` with a typed
  `WireError` taxonomy, documented byte layout and golden frames in
  `docs/wire.md`.
- Schema bundle shipped inside every packaged FMU: `<Model>.proto` (proto3,
  payload fields numbered by IR `value_reference`) and `wire.json` (format
  version, model id, step size, signals, rate groups), both deterministic and
  emitted next to the binary. The `schema` CLI verb writes the bundle from a
  `model.json`; `ProjectionError` fails packaging instead of dropping a signal.
- C++ end of the wire envelope in `runtime/src/wire.cpp`: packed little-endian
  header, CRC32/ISO-HDLC, and a portable SHA-256 model id that reproduces the
  Python vectors for `demo` and `demo_model`. `encode_frame` / `decode_frame`
  return typed `ErrorCode` failures mirroring the Python `WireError` taxonomy.
- `PYFMI_INTEROP_WIRE` string option (`protobuf` or `raw`) in
  `cmake/wire.cmake`, exposed as the `PYFMI_INTEROP_WIRE_MODE` cache variable,
  target property, and compile definition. It defaults to `protobuf` when
  libprotobuf and `protoc` are found, otherwise `raw`.
- Generated models emit `<Model>.proto`, `wire.json`, and `model_wire.cpp`. In
  `protobuf` mode the project compiles its schema with `protoc`, maps signal
  values to and from `<Model>Payload` through the protobuf reflection API, and
  builds a `wire_conformance` executable whose frames are byte-identical to
  Python `wire.encode`.
- Runtime wire tests cover the Python golden frames, round-trip, CRC, version,
  truncation, and trailing-byte failures in both wire modes; a Python/C++
  conformance test asserts frame byte identity.

### Changed

- The wheel is a platform wheel carrying the prebuilt static runtime; the
  native runtime must be built before `python -m build`.
- Non-loopback adapters ship as unavailable stubs until their library is enabled
  and their binding is implemented.
- Corrected DCP: it is ASAM X-DCP (Distributed Co-Simulation Protocol),
  implemented by DCPLib, not DDS.
