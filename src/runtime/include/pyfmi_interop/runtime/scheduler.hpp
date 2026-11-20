#pragma once

#include <cstdint>
#include <functional>
#include <string>

namespace pyfmi_interop {

enum class OverrunPolicy { Warn, Skip, Fail };

struct SchedulerConfig {
    // Nominal model step, in seconds.  Must be positive.
    double step_size = 0.001;
    // false runs as fast as possible (useful for tests and offline replay).
    bool realtime = true;
    // Busy-spin for this fraction of the step at the end of the wait window.
    // 0 disables spin-waiting.  Clamped to [0, step_size].
    double spin_margin_s = 0.0;
    // Warn: count the miss and keep the original schedule (catch up).
    // Skip: count the miss and re-anchor the next deadline to "now".
    // Fail: count the miss, fill `error`, and stop.
    OverrunPolicy overrun_policy = OverrunPolicy::Warn;
    // 0 means unbounded; stop by returning false from the step function.
    std::uint64_t max_steps = 0;
};

struct SchedulerStats {
    std::uint64_t steps = 0;
    std::uint64_t overruns = 0;
    double max_lateness_s = 0.0;
};

// Called with the simulation time at the start of the step and the step size.
// Returning false stops the run; the function may fill `error`.
using StepFn = std::function<bool(double time, double step_size, std::string& error)>;

// Optional exchange hook.  It runs immediately before the step function on
// every iteration so a standalone embedder can do ``exchange -> step`` without
// going through the FMI facade.
using ExchangeFn = std::function<bool(double time, double step_size, std::string& error)>;

// Fixed-step realtime scheduler.  The run loop allocates nothing: it holds
// only scalars, time points and a reference to the preallocated step function.
// A std::string is produced only on the error path.
class Scheduler {
public:
    explicit Scheduler(SchedulerConfig config = {});

    // Runs until max_steps, a step function failure, or a Fail overrun.
    // Returns false and fills `error` when the run stops because of a fault
    // (invalid configuration, step failure, or Fail policy overrun).
    bool run(const StepFn& step, std::string& error);

    // Overload with a transport exchange hook.  `exchange` runs before `step`
    // on every iteration; a failure stops the run and fills `error`.
    bool run(const ExchangeFn& exchange, const StepFn& step, std::string& error);

    // Statistics from the most recent run.  Reset at the start of run().
    const SchedulerStats& stats() const noexcept;

private:
    bool run_impl(const StepFn& step, const ExchangeFn* exchange, std::string& error);

    SchedulerConfig config_;
    SchedulerStats stats_;
};

// Alternative name used by standalone embedders that drive the fixed-step
// loop directly rather than through the FMI facade.
using RealtimeScheduler = Scheduler;

}  // namespace pyfmi_interop
