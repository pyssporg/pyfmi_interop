---
title: Product Breakdown — pyfmi_interop
summary: Current-state record of why the wire-format contract exists, the artifacts it promises, and how they are built, verified, and released.
---

# Product Breakdown — pyfmi_interop

Current-state record of `pyfmi_interop`: why it exists, the contracts it
promises, and how generation, packaging, verification, and release are organized.

## The Seven Layers

- `00-intent/` — why the project exists and what it refuses to become.
- `01-product/` — the artifact, realtime, and byte transport contracts.
- `02-architecture/` — layer map, the IR, and code generation.
- `03-implementation/` — the scheduler, the transport runtime, and the FMI facade.
- `04-verification/` — the test ladder and its default gate.
- `05-operation/` — local setup and release.
- `06-evolution/` — open work after the wire-only remit.
- the decision archive (`docs/archive/archive.zip`) — dated decisions, history
  only, read via `pb archive`.

## Boundary Rule

A document's home is the layer whose question it answers; information flows
downward only. Current state lives in layer leaves, history in the decision
archive, and tracking in the generated registers. This file indexes current
state only.

- Read top-down: intent, product, architecture, implementation, verification,
  operation.
- Cite other nodes by ID, never by path.
- Evolution holds candidates only; it never restates current state.

## Excludes

- Runnable examples: `examples/`.
- Generated builds: `build/` and `/tmp`.
- Generated sources and FMUs: build output, never checked in.
- The vendored FMI 2.0 headers: `third_party/fmi2/headers/`.
