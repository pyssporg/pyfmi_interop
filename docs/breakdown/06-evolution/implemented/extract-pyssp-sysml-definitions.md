---
id: IMP-003
type: imp
title: Extract the SysML vocabulary into pyssp_sysml_definitions
summary: PysspCore and artifact vocabularies install as a dependency-free artifact while the parser keeps the IR and policies
date: 2026-11-22
status: implemented
related: [ID-007]
---

# Extract the SysML vocabulary into pyssp_sysml_definitions

**Question:** can the SysML vocabulary install for external apps without dragging a parser along, while `pycps_sysml2` keeps the parser, IR, and policies?

- **Evidence:** the definitions are bundled with the parser, so an app that only reads `PysspCore` or `PyfmiInterop` must install the parser and its dependencies.
- **Evidence:** `pycps_sysml2` needs the vocabulary at parse time, and `pyfmi_sysml` will need the same definitions as the FMI composition layer.
- **Change:** the end state is a new repository `pyssp_sysml_definitions` carrying `PysspCore` and the artifact vocabularies (`PyfmiInterop`, later FMI/SoS), installable by external apps with no Python dependencies; `pycps_sysml2` depends on it and keeps the parser, IR, and policies, and `pyssp_sysml2` keeps the SSP composition layer.
- **Risk:** a cross-repo dependency and release order gate the work; the vocabulary must be byte-identical where existing sources are reused so parse results do not drift.
- **Acceptance:** a clean environment installs `pyssp_sysml_definitions` alone and reads `PysspCore` and `PyfmiInterop`; `pycps_sysml2` parses the same sources with its suite green; no vocabulary file remains bundled inside the parser.
- **Outcome:** implemented. `pyssp_sysml_definitions` 0.1.0 ships `core.sysml` (`PysspCore`) and `interop.sysml` (`PyfmiInterop`) as dependency-free package data; `pycps_sysml2` 0.4.0 depends on `pyssp-sysml-definitions>=0.1.0` and re-exports `core_definitions`/`CORE_FILE`; no vocabulary file remains bundled in the parser. Release order: definitions 0.1.0, then pycps 0.4.0.
