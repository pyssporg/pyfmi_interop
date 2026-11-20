---
id: CP-003
type: capability
title: Byte transport contract
summary: The repository defines the wire frame and one Transport interface; the loopback backend is always built, and no protocol binding ships.
date: 2026-11-19
status: current
---

# Byte transport contract

A transport carries wire frames; it does not interpret the model interface.

- **Boundary:** the repository owns the envelope and the `Transport` interface,
  not a protocol. There is no adapter catalogue or compile-gated protocol stub.
- **Frames:** exchange uses whole wire frames as non-owning byte spans; a
  backend allocates queues or buffers in `initialize()`, never in `send` or
  `receive`.
- **Loopback:** the in-process backend is always built and is the only backend
  needed for single-process tests.
- **Byte transports:** `loopback`, `udp`, and `tcp` name the byte carriers; the
  CLI lists the same names and the registry is authoritative at run time.
  Framing is the only contract this repository defines for them.
- **Deployment:** a transport endpoint is resolved per instance from the
  model's `parameter` interface (`transport`, `bind_address`, `peer_address`)
  before initialization. The process environment is consulted only when the
  model declares no parameter interface at all. `queue_depth` and `deadline_s`
  are documented keys in `resources/transport.json` that the C++ runtime does
  not consume.
- **Initialization-only:** the parameter interface is configuration, not state:
  FMI `causality="parameter"`, `variability="fixed"`, writable before
  `fmi2EnterInitializationMode`, and never a wire field. Runtime behaviour
  belongs in `in` ports (FMI `causality="input"`), not parameters.
- **Failure:** an unknown transport name or parameter value is reported and
  makes initialization fail; there is no silent fallback to loopback or
  another backend.
