---
title: Implemented
summary: Finished improvements, kept as the record of what was done.
---

# Implemented

## Contents

<!-- pb:index:start -->
<!-- GENERATED FILE — do not edit. Regenerate with `pb registers`. -->
- **IMP-002** [Adopt the parser-free Reduction seam from pyfmi_sysml2](adopt-the-parser-free-reduction-seam-from-pyfmi-sysml2.md) — Reduce once into a Reduction, restore typed start values on Variable, and drop the interop-side re-resolution
- **IMP-003** [Extract the SysML vocabulary into pyssp_sysml_definitions](extract-pyssp-sysml-definitions.md) — PysspCore and artifact vocabularies install as a dependency-free artifact while the parser keeps the IR and policies
- **IMP-004** [Rename pyfmi_sysml2 to pyfmi_interfaces with a shim](rename-pyfmi-sysml2-to-pyfmi-interfaces.md) — The shared FMI interface model and emitters ship as pyfmi_interfaces, and pyfmi_sysml2 re-exports them for one deprecation window
- **IMP-005** [Extract pyfmi_sysml from the interop sysml boundary](extract-pyfmi-sysml-from-interop.md) — A separate pyfmi_sysml composition layer loads through pycps_sysml2, reduces once, maps to ModelSpec, and calls the interop generator
- **IMP-006** [Make pyfmi_interfaces parser-free and drop interop's SysML surface](make-pyfmi-interfaces-parser-free.md) — The interface package emits from the FMI interface model, and interop loses its sysml extra, its --sysml flag, and the upstream dependency
<!-- pb:index:end -->
