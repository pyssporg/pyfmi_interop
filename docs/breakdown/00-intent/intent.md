---
id: INFO-001
type: info
title: Intent
summary: pyfmi_distributed turns a SysML v2 FMU definition into a generated C++17 realtime runtime with transport adapters, and refuses to own model equations or a master algorithm.
date: 2026-11-09
status: current
---

# Intent

`pyfmi_distributed` turns one SysML v2 definition of an FMU into an optimized
C++17 realtime runtime, binds its signals to transport adapters, and packages
the result as an FMI 2.0 CoSimulation FMU.

- **Purpose:** make the interface, schedule, and transport bindings of a
  realtime model generated and reproducible, instead of hand-written per
  project.
- **Interface, not equations:** SysML defines signals, types, rates, and
  bindings. The model's equations belong in one user `user_step` hook.
- **One runtime:** generated code implements `ModelRuntime`; the scheduler,
  transport registry, and FMI facade are reusable and model-independent.
- **Adapters are opt-in:** loopback is always built; HLA, DIS, DCP, ROS 2, and
  ED-247 are compile-gated stubs behind `PYFMI_DIST_ENABLE_*`, default OFF.
- **No SDK vendoring:** no external transport SDK is a hard build dependency.
  Enabling an adapter without its SDK fails explicitly.
- **No master algorithm:** the runtime is an FMI slave. It does not schedule
  other FMUs, own a co-simulation master, or judge results.
- **No model library:** the project does not supply equations, solver
  integration, or a Modelica model.

The artifact crosses the boundary: generated C++, a static runtime, and a
packaged `.fmu`. A tool that needs the IR consumes the canonical JSON.
