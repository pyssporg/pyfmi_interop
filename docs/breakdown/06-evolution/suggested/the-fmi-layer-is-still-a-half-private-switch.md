---
id: IMP-001
type: imp
title: The FMI layer is still a half-private switch
summary: The CLI can generate only the core facade and cannot package an adapter tree, while adapter manifests still carry fmi_layer
date: 2026-11-20
status: suggested
---

# The FMI layer is still a half-private switch

**Question:** make the FMI-layer choice a real seam again, or keep the adapter Python-only and delete every leftover switch?

- **Evidence:** `generate --sysml` always emits the core facade — the CLI calls the generator with no layer choice.
- **Evidence:** `package` can rebuild only the core facade: it injects no document or schema entries, so the adapter's `pyfmi_interfaces` `modelDescription.xml` and wire files exist only when a Python caller supplies them (`INFO-007`).
- **Evidence:** the removed switch survives in the adapter manifest — it still writes an `fmi_layer` key and rejects any other value on load.
- **Contradiction:** the intent promises one FMI facade per artifact (`INFO-001`), but the CLI produces and packages one of the two artifacts.
- **Change:** pick one. (a) add a layer option to `generate --sysml` and record enough in the adapter manifest for `package` to rebuild the FMU; or (b) give the adapter its own packaging entry point, make the CLI reject adapter trees with a clear error, and drop `fmi_layer` from the manifests.
- **Risk:** (a) pulls `pyfmi_interfaces` into the CLI import graph; (b) keeps the adapter outside the pipe-and-filter CLI. Either way the archive stays byte-deterministic (`CP-001`).
- **Acceptance:** from a clean checkout, one documented command chain per artifact yields a valid FMU with the right `modelDescription.xml`, and no manifest carries a field the public contract does not name.
