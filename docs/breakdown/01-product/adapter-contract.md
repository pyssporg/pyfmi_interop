---
id: CP-003
type: capability
title: Transport adapter contract
summary: One adapter catalogue drives the CLI and CMake gates; loopback is always built, other adapters are stubs that report unavailable.
date: 2026-11-09
status: current
---

# Transport adapter contract

An adapter is one descriptor plus one C++ implementation behind the `Transport`
interface; loopback is always built and every other adapter is opt-in.

- **Catalogue:** `adapters.py` is the only adapter list; the CLI, CMake options,
  vcpkg manifest, and documentation read it (`INFO-006`).
- **Gate:** HLA, DIS, DCP, ROS 2, and ED-247 compile only with
  `PYFMI_INTEROP_ENABLE_<NAME>=ON`; the default is OFF.
- **Stub:** a gated-off adapter still links, `available()` returns false, and
  `initialize()` fails with an actionable error.
- **Dependency:** each non-loopback descriptor records acquisition, upstream,
  pin, license, CMake package and targets, and submodule path. The build prefers
  an installed package, then `third_party/<lib>`, then FetchContent with
  `-DPYFMI_INTEROP_ALLOW_FETCH=ON`, then fails with the upstream URL. Protocol
  serialization is never reimplemented; mapping code lives in
  `runtime/src/adapters/`.
- **DCP:** ASAM X-DCP (Distributed Co-Simulation Protocol) via DCPLib; not DDS.
- **ROS 2:** system Jazzy installation only; `rclcpp` is never vendored.
- **Frames:** exchange uses preallocated `Sample` frames; adapter buffers are
  allocated in `initialize()`, never in `send` or `receive`.
- **Failure:** an unknown transport, missing library, or rejected configuration
  is reported; there is no silent fallback to another adapter.
- **Binding:** each `TransportBinding` names a signal, adapter, channel, and
  direction, and is validated against the IR before generation.
