---
id: INFO-003
type: info
title: Specification and execution IR
summary: ModelSpec is the public interface contract, BuildConfig the generation choices, and ModelDefinition the internal IR every generator reads.
date: 2026-11-20
status: current
---

# Specification and execution IR

`ModelSpec` is the public contract a caller hands to the generator;
`ModelDefinition` is the internal IR that every generator, the builder, and the
packager read.

- **Public contract:** `ModelSpec` in `core/spec.py` carries the interface only —
  name, signals, `step_size_s`, `realtime`, `interface`, `description`,
  `metadata`, and `rate_groups` — and defaults `guid` to the uuid5 of the name.
  `BuildConfig` carries the generation choices: `serialization`, `role`, and
  `prefix`. FMI parameters stay `Direction.PARAMETER` signals, set at init or
  during simulation; they are runtime configuration, never build configuration.
- **Internal IR:** `ModelDefinition`, `Signal`, and `RateGroup` in `core/ir.py`;
  `ModelSpec.to_model(config)` projects onto it. It is not the public entry
  point, and `fmi_layer` is not part of it.
- **Value references:** assigned once, gap-free, in canonical signal-name order
  by `assign_value_references`.
- **Timing:** a realtime model stores `step_size_s`; every signal rate and rate
  group must be an integer multiple of the step. An adapter has no step, so its
  declared rates are validated as integer multiples of the slowest declared
  rate, and no declared rate means no validation.
- **Types:** real, integer, boolean, and string; a string signal carries a fixed
  `capacity` so its storage can be preallocated.
- **Identity:** the GUID is a uuid5 of the model name in a fixed namespace, so
  rebuilding a model preserves its identity.
- **Serialization:** canonical JSON round-trips through `model_to_dict` and
  `model_from_dict`; `fingerprint` identifies a build. `model.json` is the
  internal build manifest written next to every generated model; the CLI reads
  that same JSON, and no separate public schema is defined.
- **Refusals:** duplicate names, duplicate value references, and misaligned
  rates raise before generation.
