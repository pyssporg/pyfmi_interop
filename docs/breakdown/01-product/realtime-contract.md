---
id: CP-002
type: capability
title: Realtime execution contract
summary: The generated runtime advances by a fixed step with preallocated frames, no allocation in the step path, and visible deadline accounting.
date: 2026-11-09
status: current
---

# Realtime execution contract

The generated runtime executes a fixed-step plan with no allocation on the step
path.

- **Fixed step:** the scheduler advances by `step_size_s`; every rate group and
  signal rate is an integer multiple of that step, validated before generation.
- **Deadline:** each step carries a deadline, and an overrun is measured and
  surfaced through the policy: `Warn` keeps the schedule, `Skip` re-anchors,
  and `Fail` stops the run.
- **Preallocation:** signal storage and the `Sample` frames exchanged with
  transports are sized once during initialization.
- **No allocation:** the numeric step path performs no heap traffic; string
  signals use a fixed capacity and are the documented transport-copy
  exception when a destination must grow.
- **Optional spin-wait:** spin-wait reduces wake-up latency at a CPU cost; it is
  an option, not the default.
- **Order:** the scheduler consumes inputs, runs `user_step`, publishes outputs,
  then accounts for the deadline.
- **Visibility:** an overrun or transport failure is reported; it is never
  disguised as a normal step.
