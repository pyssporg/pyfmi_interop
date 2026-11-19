---
id: INFO-003
type: info
title: Execution IR
summary: ModelDefinition is the single source of truth for signals, value references, and rates.
date: 2026-11-09
status: current
---

# Execution IR

`ModelDefinition` is the single source of truth for signals, value references,
and rates; every generator reads it.

- **Core types:** `ModelDefinition`, `Signal`, and `RateGroup` in `ir.py`.
- **Value references:** assigned once, gap-free, in canonical signal-name order
  by `assign_value_references`.
- **Timing:** stored in seconds as `step_size_s` and periods; every signal rate
  and rate group must be an integer multiple of the step.
- **Types:** real, integer, boolean, and string; a string signal carries a fixed
  `capacity` so its storage can be preallocated.
- **Identity:** the GUID is a uuid5 of the model name in a fixed namespace, so
  rebuilding a model preserves its identity.
- **Serialization:** canonical JSON round-trips through `model_to_dict` and
  `model_from_dict`; `fingerprint` identifies a build.
- **Refusals:** duplicate names, duplicate value references, and misaligned
  rates raise before generation.
