---
id: CP-001
type: capability
title: Artifact contract
summary: A packaged model is a deterministic FMI 2.0 CoSimulation FMU carrying one generated realtime binary and the IR's variable set.
date: 2026-11-19
status: current
---

# Artifact contract

A packaged model is a valid FMI 2.0 CoSimulation FMU with deterministic bytes
and one generated realtime binary.

- **Archive layout:** `modelDescription.xml` at the zip root; the built shared
  library under `binaries/<platform>/`.
- **Model identifier:** the FMI `modelIdentifier` equals the generated model
  name and the binary stem in the archive.
- **Variables:** every `ScalarVariable` has a unique name and a unique value
  reference taken from the IR (`INFO-003`). Deployment parameters are emitted
  with `causality="parameter"`, `variability="fixed"`, and their authored
  `start` value.
- **Identity:** the GUID is the stable uuid5 derived from the model name
  (`INFO-003`); the wire model id hashes INPUT/OUTPUT signals only.
- **Wire projection:** parameters are configuration, never payload fields, so
  the descriptor, both payload codecs, and the model id exclude them. The
  remaining INPUT/OUTPUT fields keep their value references as field numbers.
- **Resources:** canonical `model.json` and `runtime.json` under `resources/`,
  plus the `<Model>.proto` and `wire.json` schema bundle next to the binary, so
  the archive is self-describing.
- **Determinism:** packaging sorts entries, fixes file modes and timestamps to
  a constant, and emits byte-identical archives for equal inputs.
- **Validity:** the document has one `CoSimulation` element and declares its
  outputs index-ordered in `ModelStructure` before the archive is written.
