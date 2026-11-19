---
id: INFO-006
type: info
title: Transport runtime
summary: runtime/ exposes one Transport interface, one registry, the always-built loopback adapter, and compile-gated adapter stubs.
date: 2026-11-09
status: current
---

# Transport runtime

`runtime/` exposes one `Transport` interface and one registry; loopback is
always built and the gated adapters are stubs by default.

- **Interface:** `initialize`, `finalize`, `available`, `send`, and `receive`;
  exchange uses the preallocated `Sample` frame.
- **Configuration:** `TransportConfig` carries name, endpoint, timeout, and an
  ordered key/value option list; it may allocate, but only in `initialize`.
- **Registry:** `make_transport` maps a catalogue name to an implementation and
  lists the known names on an unknown request.
- **Loopback:** stores signals in preallocated frames for single-process tests
  and runs without a network or SDK.
- **Gated stubs:** HLA, DIS, DCP, ROS 2, and ED-247 compile behind
  `PYFMI_INTEROP_ENABLE_*`, default OFF; a stub links and reports unavailable.
- **Libraries:** protocol serialization comes from prebuilt upstream libraries
  (OpenRTI, open-dis-cpp, DCPLib, `rclcpp`, ED247_LIBRARY); mapping code lives
  in `runtime/src/adapters/`. `cmake/adapters.cmake` prefers an installed
  package, then a `third_party/<lib>` submodule, then FetchContent with
  `-DPYFMI_INTEROP_ALLOW_FETCH=ON`, then fails with the upstream URL.
- **DCP:** ASAM X-DCP (Distributed Co-Simulation Protocol) via DCPLib; not DDS.
- **No fallback:** a missing library or rejected configuration fails
  initialization; the runtime does not substitute loopback.
- **Adding one:** one descriptor, one `.cpp`, one header, and the CMake gate
  (`CP-003`).
