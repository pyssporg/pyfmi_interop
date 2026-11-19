---
title: Product
summary: The artifact, realtime execution, and byte transport contracts a generated model promises.
---

# Product

What a consumer may rely on: the packaged FMU, the realtime step contract, and
the byte transport boundary.

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **CP-001** [Artifact contract](artifact-contract.md) — A packaged model is a deterministic FMI 2.0 CoSimulation FMU carrying one generated realtime binary and the IR's variable set.
- **CP-002** [Realtime execution contract](realtime-contract.md) — The generated runtime advances by a fixed step with preallocated frames, no allocation in the step path, and visible deadline accounting.
- **CP-003** [Byte transport contract](adapter-contract.md) — The repository defines the wire frame and one Transport interface; the loopback backend is always built, and no protocol binding ships.
<!-- pb:index:end -->
