---
title: Product
summary: The artifact, realtime execution, and transport adapter contracts a generated model promises.
---

# Product

What a consumer may rely on: the packaged FMU, the realtime step contract, and
the behaviour of a transport adapter.

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **CP-001** [Artifact contract](artifact-contract.md) — A packaged model is a deterministic FMI 2.0 CoSimulation FMU carrying one generated realtime binary.
- **CP-002** [Realtime execution contract](realtime-contract.md) — The generated runtime advances by a fixed step with preallocated frames, no allocation in the step path, and visible deadline accounting.
- **CP-003** [Transport adapter contract](adapter-contract.md) — One adapter catalogue drives the CLI and CMake gates; loopback is always built, other adapters are stubs that report unavailable.
<!-- pb:index:end -->
