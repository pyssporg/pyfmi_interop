---
id: INFO-006
type: info
title: Transport runtime
summary: runtime/ exposes one Transport interface and one registry, with the always-built in-process loopback backend and no protocol binding.
date: 2026-11-09
status: current
---

# Transport runtime

`runtime/` exposes one `Transport` interface and one registry; the in-process
loopback backend is always built, and protocol bindings are not part of this
repository.

- **Interface:** `initialize`, `finalize`, `available`, `send`, and `receive`;
  exchange uses the preallocated `Sample` frame.
- **Configuration:** `TransportConfig` carries name, endpoint, timeout, and an
  ordered key/value option list; it may allocate, but only in `initialize`.
- **Registry:** `make_transport` maps a known name to an implementation and
  lists the known names on an unknown request.
- **Loopback:** stores signals in preallocated frames for single-process tests
  and runs without a network or SDK.
- **Byte transports:** `udp`, `tcp`, and `unix` name the carriers of a wire
  frame; the frame contract is `docs/wire.md` and the transport itself is
  outside this repository.
- **No fallback:** a missing backend or rejected configuration fails
  initialization; the runtime does not substitute loopback.
