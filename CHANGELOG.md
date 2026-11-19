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
