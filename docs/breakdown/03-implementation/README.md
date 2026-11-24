---
title: Implementation
summary: The scheduler, the transport runtime, and the FMI facade that execute a generated model.
---

# Implementation

How the reusable runtime executes a generated model, exchanges wire frames,
and exposes the FMI entry points.

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **INFO-005** [Realtime scheduler](scheduler.md) — The scheduler owns the fixed-step loop, preallocated frames, and deadline accounting.
- **INFO-006** [Transport runtime](transport.md) — src/runtime/ exposes one Transport interface and one registry; loopback lives there, and the UDP, TCP, and Unix datagram backends live in src/transport/.
- **INFO-007** [FMI facade](fmi-facade.md) — The FMI 2.0 facade maps fmi2 functions onto one ModelRuntime and contains no model equations.
<!-- pb:index:end -->
