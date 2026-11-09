---
id: INFO-005
type: info
title: Realtime scheduler
summary: The scheduler owns the fixed-step loop, preallocated frames, and deadline accounting.
date: 2026-11-09
status: current
---

# Realtime scheduler

The scheduler owns the clock, the fixed-step loop, frame reuse, and deadline
accounting; it never contains model behaviour.

- **Step:** advance by `step_size_s`, consume inputs, call `user_step`, publish
  outputs, then measure completion against the deadline.
- **Frames:** one preallocated `Sample` per signal count is reused every step;
  `values` and `valid` are sized during initialization.
- **Allocation:** initialization may allocate; the numeric step path does not.
  String signals write into their fixed capacity; a transport copy that must
  grow a destination string is the documented exception.
- **Deadline policy:** the scheduler counts each overrun and applies `Warn`
  (keep the schedule), `Skip` (re-anchor the next deadline), or `Fail` (stop
  with an error); a late step is counted rather than hidden.
- **Spin-wait:** an optional mode trades CPU for lower wake-up latency; it is
  not the default and does not change the step semantics.
- **Thread:** the standalone scheduler runs the step loop on the realtime
  thread; the FMI facade is synchronous and calls `ModelRuntime::step` on the
  caller's thread.
- **Failure:** a transport or hook failure is surfaced as an error; the
  scheduler does not switch transports or skip a step silently.
