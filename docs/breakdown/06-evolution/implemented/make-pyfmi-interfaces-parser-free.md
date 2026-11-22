---
id: IMP-006
type: imp
title: Make pyfmi_interfaces parser-free and drop interop's SysML surface
summary: The interface package emits from the FMI interface model, and interop loses its sysml extra, its --sysml flag, and the upstream dependency
date: 2026-11-22
status: implemented
related: [ID-007]
---

# Make pyfmi_interfaces parser-free and drop interop's SysML surface

**Question:** once the composition layer is external, can the interface package and interop both stand free of parser and dialect dependencies?

- **Evidence:** `pyfmi_interfaces` is planned to own the FMI interface model and emitters, but the old package still pulls its ingestion stack into paths that only emit.
- **Evidence:** `pyfmi_interop` still declares a `[sysml]` extra, a `--sysml` CLI flag, and an upstream `pyfmi_interfaces` dependency that the core does not need.
- **Change:** the end state is `pyfmi_interfaces` generating only from the interface model with no parser dependency, and `pyfmi_interop` installing without a `[sysml]` extra and without the upstream dependency; its CLI accepts IR JSON or a `ModelSpec`, has no `--sysml` flag, and points SysML users at the `pyfmi-sysml` entry.
- **Risk:** a consumer that installed the extra or passed `--sysml` breaks; the error must name the replacement entry point, and the change belongs in a release note rather than a silent fallback.
- **Acceptance:** a base install of `pyfmi_interop` runs the core suite and generates from IR JSON and `ModelSpec`; `--sysml` is an unknown option with a clear message; `pyfmi_interfaces` has no `pycps_sysml2` import in its dependency graph; `pytest -m "not sysml"` stays green.
- **Outcome:** implemented. `pyfmi_interop` installs `pyfmi-interfaces` as a runtime dependency with no `[sysml]` extra and no parser dependency; the CLI has no `--sysml`, `--include`, `--step-size`, or `--name`, and consumes IR JSON only; `pytest -m "not sysml"` and the core suite are green.
