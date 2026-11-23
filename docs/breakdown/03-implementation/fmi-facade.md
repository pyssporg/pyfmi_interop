---
id: INFO-007
type: info
title: FMI facade
summary: Each artifact's FMI 2.0 facade maps fmi2 functions onto one ModelRuntime and contains no model equations; the core and the adapter never share a binary.
date: 2026-11-20
status: current
---

# FMI facade

Each artifact's FMI 2.0 facade maps `fmi2*` entry points onto one `ModelRuntime`
instance and contains no model equations.

- **One facade per artifact:** the core emits the interop facade (checked-in
  `fmi2_cs_api.cpp` plus `packaging.render_model_description`); the adapter
  generator in `pyfmi_interop.core.adapter` takes its interface, headers, and
  model description from `pyfmi_interfaces` and links the runtime without
  whole-archive. `write_adapter_tree` is its public writer;
  `pyfmi_sysml.generate_adapter` calls it from the composition layer. Both
  export the same `fmi2*` ABI, so they never share a binary.
- **No declared step:** the adapter asks the emitter for a model description
  with `include_default_experiment=False`; no XML post-processing removes it,
  and the emitted document has no `DefaultExperiment`.
- **Create and destroy:** instantiation calls the generated
  `pyfmi_interop_create_model`; destruction releases it with the matching
  destroy function. Instantiation does not open a transport.
- **Initialization:** `fmi2EnterInitializationMode` opens the transport from the
  generated parameter members, so values written in the instantiated state are
  visible. Those parameters are initialization-only configuration, never wire
  fields; runtime behaviour belongs in `in` ports. The runtime resolves
  parameter names per instance and never hardcodes the parameter port name.
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
