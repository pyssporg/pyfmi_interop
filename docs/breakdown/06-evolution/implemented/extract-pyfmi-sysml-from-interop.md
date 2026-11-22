---
id: IMP-005
type: imp
title: Extract pyfmi_sysml from the interop sysml boundary
summary: A separate pyfmi_sysml composition layer loads through pycps_sysml2, reduces once, maps to ModelSpec, and calls the interop generator
date: 2026-11-22
status: implemented
related: [ID-007]
---

# Extract pyfmi_sysml from the interop sysml boundary

**Question:** can one composition layer own the FMI family's SysML entry, leaving `pyfmi_interop` with an interface specification and no parser?

- **Evidence:** `src/pyfmi_interop/sysml/` currently holds `parse`, `generate_adapter`, the `pyfmi_interfaces` FMI layer, and the bundled definitions, so the generator repository also owns ingestion.
- **Evidence:** interop already accepts a `ModelSpec` for the interop facade, so the reduction-to-spec step is the only missing hand-off for an external composition layer.
- **Change:** the end state is a new repository `pyfmi_sysml` that loads through `pycps_sysml2`, reduces once to the parser-free `Reduction`, maps it to `ModelSpec`, and calls the interop generator; it publishes the `pyfmi-sysml` entry point and the FMI adapter flow, while `pyfmi_interop` carries no `sysml/` subpackage.
- **Risk:** the split moves tests and the CLI entry point across repositories; the reduction seam must stay single-parse so the composition layer cannot re-resolve the export unit.
- **Acceptance:** `pyfmi-sysml` generates and packages an adapter from a SysML source using the interop generator; `pyfmi_interop` imports no SysML package; one parse per run is proven by a reduction-once check; the moved sysml tests pass in the new repository.
- **Outcome:** implemented. `pyfmi_sysml` owns `parse`, `load_architecture`, `model_from_architecture`, `model_from_sysml`, `ParsedModel`, `generate_adapter`, and the `PyfmiInterop` vocabulary; interop's `sysml/` tree, `psysml2` shim, and `definitions` facade are gone; the moved parse-once and adapter tests pass in `pyfmi_sysml`.
