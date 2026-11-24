---
id: INFO-001
type: info
title: Intent
summary: pyfmi_interop emits a realtime model, an adapter model, and an FMU from an interface specification, owning serialization and transport seams but not SysML ingestion or model semantics.
date: 2026-11-22
status: current
---

# Intent

`pyfmi_interop` takes an interface specification of an FMU and turns it into a
realtime model, an adapter model, and an FMI 2.0 CoSimulation FMU. It is
SysML-free: the specification is IR JSON or a `ModelSpec`, and SysML ingestion
lives in the `pyfmi_sysml` composition layer.

- **The job:** take the interface specification — names, types, value
  references, directions, and, for the realtime model, step metadata — and emit
  the generated sources, the model description, and the FMU; no value meaning leaves the endpoint.
- **Two generated roles:** the same interface yields the realtime model and an
  adapter model that moves values on and off the byte transport. The adapter
  has no equations and no `user_step`.
- **Causality sets the direction:** an FMI `input` is published to the wire, an
  FMI `output` is consumed from it, and a `parameter` is never published.
- **One message per interface:** its fields are every input and output signal
  field of every port, numbered `1..n` in canonical signal-name order; parameters
  carry no wire field. FMI value references stay a separate namespace owned by the
  generated interface, so adding a parameter never renumbers the wire.
- **One interface model:** the FMI interface model and its emitters live in
  `pyfmi_interfaces`; the interop generator and the adapter consume that model
  rather than re-deriving declarations.
- **Two ends:** a Python end and a C++ end meet at the byte layer and are
  tested against the same conformance vectors, so the format has one reading.
- **One FMI facade per artifact:** the core emits its own facade for the realtime
  model, and the adapter takes its C interface, headers, and model description
  from the shared FMI interface model and emitters in `pyfmi_interfaces`. Both
  export the same `fmi2*` ABI and never share a binary; this repository owns the wire plane.
- **Two registered seams:** serialization selects one schema authority per backend
  — protobuf canonical, `packed` second — while transports select loopback, UDP,
  TCP, or Unix datagrams by name at runtime. Framing stays single-authority and versioned: wire
  version 2 adds `payload_format`, field numbers are append-only, reserved stays reserved.
- **Deployment is a parameter interface:** deployment-varying transport
  configuration arrives as FMI parameters with default values, authored through
  the composition layer, and the master binds it before initialization; structural
  facts stay build-time attributes. The environment is only a fallback when a
  model declares no parameter interface; endpoints are never SSD/SSP content, so an SSP stays portable.
- **SysML is composed outside:** `pyfmi_sysml` loads through `pycps_sysml`, reduces
  once to the parser-free `Reduction`, maps it to `ModelSpec`, and calls generation;
  vocabulary lives in `pyssp_sysml_definitions`. `pyfmi_interop` declares no
  `[sysml]` extra, no `--sysml` flag, and no upstream parser dependency.
- **No semantics:** the repository does not step, schedule, or judge models, and
  does not translate between protocols. A model interface in equals the same out.
- **Non-goals:** RPR, DIS, HLA/RTI, DCP, ED-247, and ROS 2 vocabularies and their
  translation; radio or medium models; time management; mission coordination; the
  federation-endpoint role; and a catalogue of protocol adapters. Each is a separate repository.

The artifact crosses the boundary: the generators, the protobuf schema and its
Python and C++ bindings, the framing code, and the transport backends.
