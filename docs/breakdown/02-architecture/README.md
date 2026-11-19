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
- **INFO-002** [Layer and module map](layers.md) — Python generates, C++ executes, and the generated model joins them through the ModelRuntime interface and one IR.
- **INFO-003** [Execution IR](ir.md) — ModelDefinition is the single source of truth for signals, value references, and rates.
- **INFO-004** [Code generation](codegen.md) — codegen emits a C++17 source tree and one CMakeLists.txt per model, with typed signals, publish/consume hooks, user_step, and the factory.
<!-- pb:index:end -->
