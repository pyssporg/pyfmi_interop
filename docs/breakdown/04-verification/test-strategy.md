---
id: TEST-001
type: test
title: Test strategy
summary: Eight pytest markers grade the fault class; the SysML-free suite covers the core and CLI, with generated sources, the CMake build, and the packed FMU as the artifacts under test.
date: 2026-11-20
status: current
---

# Test strategy

Tests are organized by the artifact they can break, not by module; each level
owns a distinct fault class. `tests/core/` exercises the SysML-free core, and
`tests/test_cli.py` plus the shared `tests/conftest.py` cover the command
surface. SysML ingestion, export selection, and the parse-once adapter flow are
tested in `pyfmi_sysml`; this repository imports no SysML package and carries no
test dependency on `pyfmi-sysml`.

- **static:** layering, the single wire contract, and fixture or provenance
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
- **sysml:** declared but unused here; it stays reserved for suites that opt
  into SysML ingestion.
- **slow:** an orthogonal qualifier for long native runs.

The `sysml` marker stays declared in `pyproject.toml`. Default gate:
`python -m pytest -m "not sysml"` plus `ctest` after the native build, on
Python 3.11 and 3.12; the full suite is `python -m pytest`. The single-parse
rule is pinned by the moved `pyfmi_sysml` tests: `parse` calls `to_reduction`
once and produces one `ParsedModel`, and `generate_adapter` rejects anything
else instead of reloading the source or re-resolving the export unit.
Goldens are compared, never regenerated in CI.
