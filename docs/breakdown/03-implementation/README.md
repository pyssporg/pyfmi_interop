---
title: Implementation
summary: The scheduler, the transport runtime, and the FMI facade that execute a generated model.
---

# Implementation

How the reusable runtime executes a generated model, exchanges transport frames,
and exposes the FMI entry points.

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **INFO-005** [Realtime scheduler](scheduler.md) — The scheduler owns the fixed-step loop, preallocated frames, and deadline accounting.
- **INFO-006** [Transport runtime](transport.md) — runtime/ exposes one Transport interface, one registry, the always-built loopback adapter, and compile-gated adapter stubs.
- **INFO-007** [FMI facade](fmi-facade.md) — The FMI 2.0 facade maps fmi2 functions onto one ModelRuntime and contains no model equations.
<!-- pb:index:end -->
