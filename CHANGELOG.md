# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed

- The wheel is a platform wheel carrying the prebuilt static runtime; the
  native runtime must be built before `python -m build`.
- Non-loopback adapters ship as unavailable stubs until their library is enabled
  and their binding is implemented.
- Corrected DCP: it is ASAM X-DCP (Distributed Co-Simulation Protocol),
  implemented by DCPLib, not DDS.
