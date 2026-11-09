---
id: INFO-010
type: info
title: Adapter roadmap
summary: The next work replaces compile-gated stubs with tested bindings, one adapter at a time, while loopback stays stable.
date: 2026-11-09
status: current
---

# Adapter roadmap

The next work is to replace compile-gated adapter stubs with tested bindings,
one adapter at a time, without changing the IR or codegen boundary.

- **Loopback:** stays stable and remains the default and the test transport.
- **HLA:** implement the RTI binding against a lightweight test federate; keep
  the option OFF by default.
- **DIS:** implement PDU exchange against a loopback or recorded packet oracle;
  no external SDK is required.
- **DCP:** implement the ASAM X-DCP binding with DCPLib, slave and master
  modes; DDS is a separate transport and is not DCP. Keep the option OFF by
  default.
- **ROS 2:** bind rclcpp topics with callback exchange outside the step
  deadline.
- **ED-247:** bind configured streams with deadline-checked reads and writes.
- **Gate:** each adapter lands with a CI job that is optional while its SDK is
  absent; the default build still depends on no external SDK.
