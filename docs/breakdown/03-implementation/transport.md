---
id: INFO-006
type: info
title: Transport runtime
summary: src/runtime/ exposes one Transport interface and one registry; loopback lives there, and the UDP, TCP, and Unix datagram backends live in src/transport/.
date: 2026-11-24
status: current
---

# Transport runtime

`src/runtime/` exposes one `Transport` interface and one registry; the in-process
loopback backend is always built there, and the UDP, TCP, and Unix datagram
backends are built into the separate static library `pyfmi_interop_transport`
from `src/transport/`. Protocol bindings are not part of this repository.

- **Interface:** `initialize(const std::string& uri)`, `finalize`, `send`,
  `receive`, and `stats`; `send` takes a `ByteSpan` of one whole wire frame and
  `receive` returns the newest queued frame as bytes.
- **Non-blocking:** `send` returns false when the frame would block or no peer
  is known; `receive` returns an empty optional when no frame is queued. The
  step loop never waits for a peer.
- **Registry:** `make_transport` resolves a bare scheme or a URI scheme to one
  backend and `transport_names` returns the sorted names; an unknown scheme
  throws `TransportError` listing every registered name.
- **Loopback:** an in-process byte-frame transport for single-process tests; it
  needs no network or SDK.
- **Byte transports:** `loopback`, `udp`, `tcp`, and `unix` name the carriers
  of a wire frame; the frame contract is `docs/wire.md`. The URI grammar is
  parsed in `src/transport/src/transport_uri.cpp`.
- **Unix datagrams:** `unix` is `AF_UNIX` + `SOCK_DGRAM`, one datagram per
  frame. A pathname bind unlinks a stale entry only when it is a socket; an
  abstract `@name` lives in the kernel namespace and needs no cleanup.
- **Linkage:** the UDP, TCP, and Unix backends register from static
  initializers, so a consumer links `libpyfmi_interop_transport.a` with
  whole-archive.
- **No fallback:** a missing backend or rejected configuration fails
  initialization; the runtime does not substitute loopback.
