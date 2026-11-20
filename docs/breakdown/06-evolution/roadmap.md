---
id: INFO-010
type: info
title: Wire format roadmap
summary: The wire-only remit landed in 0.3.0; the current release is 0.5.0 and no adapter catalogue or protocol binding returns.
date: 2026-11-19
status: current
---

# Wire format roadmap

No wire-format work remains open. The wire-only remit shipped in 0.3.0; the
current release is 0.5.0 (`pyfmi_interop.__version__`, `CHANGELOG.md`).

- **Release:** 0.3.0 was cut from the landed wire contract; later releases keep
  the same remit, and no adapter catalogue or protocol binding returns.
- **Gate:** the Python suite, lint, the native CTest run, and an empty
  `git submodule status` stay green.
