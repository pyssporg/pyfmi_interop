---
id: INFO-010
type: info
title: Wire format roadmap
summary: The next work lands one protobuf wire format with length, CRC32, and version framing, its Python and C++ ends, and removes the adapter surface.
date: 2026-11-19
status: current
---

# Wire format roadmap

The next work lands the wire contract and removes the adapter surface it
replaces; no adapter is carried forward.

- **Removal:** delete `src/pyfmi_interop/adapters.py`, `runtime/src/adapters/*`,
  `cmake/adapters.cmake`, every `PYFMI_INTEROP_ENABLE_*` option, the
  `third_party/{OpenRTI,DCPLib,ED247_LIBRARY}` submodules with their
  `.gitmodules` entries, and the adapter catalogue; replace `docs/adapters.md`
  with `docs/wire.md` and the `adapters` CLI verb with `transports`.
- **Schema:** one versioned protobuf definition of the model interface and the
  sample message, with generated Python and C++ bindings and no hand-written
  codec.
- **Framing:** length prefix, CRC32, and format version, specified once and
  implemented identically at both ends.
- **Conformance:** shared byte vectors both ends reproduce; a mismatch fails
  the test rather than starting a negotiation.
- **Gate:** the Python-only and C++ round trips pass in CI before the adapter
  code is deleted.
