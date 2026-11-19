---
id: INFO-007
type: info
title: FMI facade
summary: The FMI 2.0 facade maps fmi2 functions onto one ModelRuntime and contains no model equations.
date: 2026-11-19
status: current
---

# FMI facade

The FMI 2.0 facade maps `fmi2*` entry points onto one `ModelRuntime` instance
and contains no model equations.

- **Create and destroy:** instantiation calls the generated
  `pyfmi_interop_create_model`; destruction releases it with the matching
  destroy function. Instantiation does not open a transport.
- **Initialization:** `fmi2EnterInitializationMode` opens the transport from the
  generated parameter members, so values written in the instantiated state are
  visible. The runtime resolves parameter names per instance and never hardcodes
  the parameter port name.
- **Types:** real, integer, boolean, and string map to the IR and runtime
  `DataType`; the FMI ABI owns the pointer lifetimes.
- **Causality:** inputs are writable, outputs readable, and parameters readable
  and writable in the instantiated state; writing a fixed parameter after
  initialization returns `fmi2Error`, as does a direction mismatch.
- **Step:** `fmi2DoStep` advances the runtime by the communication step on the
  caller's thread; it is synchronous and creates no background thread.
- **Scheduler:** the standalone realtime scheduler is a separate runtime
  component; the synchronous FMI facade does not drive it (`INFO-005`).
- **Reset:** initialization restores initial values and clears outputs.
- **Errors:** unknown value references, unavailable transports, and rejected
  configurations become a status or error string, never a crash.
- **Boundary:** the facade knows FMI, the runtime knows the schedule, and the
  generated model knows the signals; none absorbs another's job.
