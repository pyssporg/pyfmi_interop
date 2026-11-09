---
id: TEST-001
type: test
title: Test strategy
summary: Seven pytest markers grade the fault class; generated sources, the CMake build, and the packed FMU are the artifacts under test.
date: 2026-11-09
status: current
---

# Test strategy

Tests are organized by the artifact they can break, not by module; each level
owns a distinct fault class.

- **static:** layering, the single adapter catalogue, and fixture or provenance
  rules that hold without executing the package.
- **unit:** one object's behaviour, no artifact written; the IR validation and
  timing rules are asserted directly.
- **component:** a generated C++ source or FMI XML is the unit under test,
  compared against a reviewed golden.
- **contract:** two directions must agree: IR JSON round-trip, and the
  generated model ABI against the runtime headers.
- **system:** the CLI and the native build end to end, from IR input to a
  packaged `.fmu`.
- **cpp:** requires a C++17 toolchain and CMake; builds the runtime and a
  generated model.
- **slow:** an orthogonal qualifier for long native runs, excluded from the
  default gate.

Default gate: `python -m pytest -m "not slow"` plus `ctest` after the native
build, on Python 3.11 and 3.12. Goldens are compared, never regenerated in CI.
