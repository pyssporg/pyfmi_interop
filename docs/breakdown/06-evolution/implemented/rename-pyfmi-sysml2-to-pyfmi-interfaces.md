---
id: IMP-004
type: imp
title: Rename pyfmi_sysml2 to pyfmi_interfaces with a shim
summary: The shared FMI interface model and emitters ship as pyfmi_interfaces, and pyfmi_sysml2 re-exports them for one deprecation window
date: 2026-11-22
status: implemented
related: [ID-007]
---

# Rename pyfmi_sysml2 to pyfmi_interfaces with a shim

**Question:** can the shared FMI layer take a SysML-free name without breaking the consumers that still import the old one?

- **Evidence:** `pyfmi_sysml2` names a dialect even though its job is the FMI interface model and emitters, so the name keeps signalling that the layer is SysML-bound.
- **Evidence:** the adapter and the planned composition layer both consume this package, so a rename has more than one consumer from the first release.
- **Change:** the end state is the package `pyfmi_interfaces` owning the FMI interface model and emitters; `pyfmi_sysml2` remains as a re-export shim for one deprecation window, and every in-repo consumer imports the new name.
- **Risk:** two importable names during the window can drift if new code lands in the shim; the shim must contain no logic, only re-exports.
- **Acceptance:** `import pyfmi_interfaces` exposes the same public API as the old package, `import pyfmi_sysml2` re-exports it, no release artifact requires the old name, and the shim retires after the stated window.
- **Outcome:** implemented. `pyfmi_interfaces` 0.5.1 owns the FMI interface model and emitters; `pyfmi_sysml2` is a deprecated re-export shim for one window; `pyfmi_interop` depends on `pyfmi-interfaces>=0.5.1`, and every in-repo consumer imports the new name.
