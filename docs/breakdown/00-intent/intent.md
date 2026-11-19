---
id: INFO-001
type: info
title: Intent
summary: pyfmi_interop emits a realtime model and a wire-carrying adapter from a SysML part definition, owning serialization and transport seams, not model semantics.
date: 2026-11-19
status: current
---

# Intent

`pyfmi_interop` turns one SysML v2 part definition into a realtime model and an
adapter model, and carries their interface across one versioned byte format: a
Python end encodes it, a C++ end decodes it, and neither end interprets the
model.

- **The job:** take the part-definition interface — names, types, value
  references, directions, and step metadata — and carry it across the wire in
  one format. Nothing about what the values mean leaves the endpoint.
- **Two generated roles:** the same interface yields the realtime model and an
  adapter model that moves values on and off the byte transport. The adapter
  has no equations and no `user_step`.
- **Causality sets the direction:** an FMI `input` is published to the wire, an
  FMI `output` is consumed from it, and a `parameter` is never published.
- **One message per part definition:** its fields are every signal field of
  every port, the field number is the value reference, and field order is the
  canonical signal-name order the value references are assigned in.
- **Two ends:** a Python end and a C++ end meet at the byte layer and are
  tested against the same conformance vectors, so the format has one reading.
- **Two registered seams:** serialization selects one schema authority per
  backend — protobuf canonical, `packed` second — while transports select
  loopback, UDP, or TCP by name at runtime. Framing stays single-authority and
  versioned: wire version 2 adds `payload_format`, field numbers are
  append-only, and the reserved range stays reserved.
- **Deployment stays out of the model:** transport endpoints come from the
  environment or a manifest, never SSD/SSP content, so an SSP stays portable.
- **No semantics:** the repository does not step, schedule, or judge models,
  and does not translate between protocols. A model interface in equals the
  same model interface out.
- **Non-goals:** RPR, DIS, HLA/RTI, DCP, ED-247, and ROS 2 vocabularies and
  their translation; radio or medium models; time management; mission
  coordination; the federation-endpoint role; and a catalogue of protocol
  adapters. Each is a separate repository.

The artifact crosses the boundary: the generators, the protobuf schema and its
Python and C++ bindings, the framing code, and the transport backends.
