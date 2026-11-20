---
title: Architecture
summary: The layer map, the single IR, and the code generator that turns it into a realtime model.
---

# Architecture

How the Python generator, the C++ runtime, and the generated model are divided,
and why they meet at one IR and one interface.

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **INFO-002** [Layer and module map](layers.md) — A SysML-free core and a SysML boundary generate, C++ executes, and the generated model joins them through ModelRuntime and one IR.
- **INFO-003** [Specification and execution IR](ir.md) — ModelSpec is the public interface contract, BuildConfig the generation choices, and ModelDefinition the internal IR every generator reads.
- **INFO-004** [Code generation](codegen.md) — core/codegen emits a C++17 source tree and one CMakeLists.txt per model, with typed signals, publish/consume hooks, user_step, and the factory.
<!-- pb:index:end -->
