---
id: INFO-001
type: info
title: Intent
summary: pyfmi_interop puts one model interface on one versioned wire format, with a Python end and a C++ end, and refuses to own semantics.
date: 2026-11-19
status: current
---

# Intent

`pyfmi_interop` puts one model interface on one versioned wire format: a
Python end encodes it, a C++ end decodes it, and neither end interprets the
model.

- **The job:** take the model interface — names, types, value references,
  directions, and step metadata — and carry it across the wire in one format.
  Nothing about what the values mean leaves the endpoint.
- **Two ends:** a Python end and a C++ end meet at the byte layer and are
  tested against the same conformance vectors, so the format has one reading.
- **Canonical payload:** protobuf carries the model interface and the sample
  values. The schema is the contract and changes by version, never in place.
- **Framing is ours:** each message is length-delimited, CRC32-checked, and
  tagged with a format version. Framing is the only layer this repository
  defines beyond the payload; transport, medium, and discovery belong
  elsewhere.
- **No semantics:** the repository does not step, schedule, or judge models,
  and does not translate between protocols. A model interface in equals the
  same model interface out.
- **Non-goals:** HLA/RTI conformance, DCP, ED-247, and ROS 2 bindings; DIS as a
  canonical vocabulary; radio or medium models; time management; mission
  coordination; the federation-endpoint role; and an adapter catalogue.

The artifact crosses the boundary: a protobuf schema, its generated Python and
C++ bindings, and the framing code that carries them.
