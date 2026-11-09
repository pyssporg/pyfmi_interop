---
id: INFO-009
type: info
title: Release
summary: Tag after a green matrix, build the native runtime first, then build and guard the platform wheel and sdist.
date: 2026-11-09
status: current
---

# Release

A release is a platform wheel built after the native runtime, tagged only after
the test matrix is green.

- **Version:** single-sourced from `pyfmi_distributed.__version__` and read by
  setuptools through `dynamic = ["version"]`.
- **Preconditions:** `main` is green on 3.11 and 3.12 and the checkout is clean.
- **Native first:** `cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release`
  then `cmake --build build`.
- **Artifacts:** `python -m build --wheel --sdist`; the wheel tag is
  `py3-none-<platform>`.
- **Metadata guard:** exactly one wheel and one sdist, no `0.0.0`, the wheel
  contains `_runtime/libpyfmi_distributed_runtime.a` and the public headers.
- **Tag guard:** a `v<version>` tag must equal the imported `__version__`.
- **Publish:** upload `dist/` and attach it to the GitHub release with
  `fail_on_unmatched_files: true`.
