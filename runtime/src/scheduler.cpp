#include "pyfmi_interop/runtime/scheduler.hpp"

#include <chrono>
#include <string>
#include <thread>

namespace pyfmi_interop {
namespace {

using Clock = std::chrono::steady_clock;
using Seconds = std::chrono::duration<double>;

void wait_until(Clock::time_point deadline, double spin_margin_s) {
    if (spin_margin_s <= 0.0) {
        std::this_thread::sleep_until(deadline);
        return;
    }

    const auto spin_start =
        deadline - std::chrono::duration_cast<Clock::duration>(Seconds(spin_margin_s));
    if (Clock::now() < spin_start) {
        std::this_thread::sleep_until(spin_start);
    }
    while (Clock::now() < deadline) {
        // Deliberate spin-wait: only the last spin_margin_s of the step.
    }
}

}  // namespace

Scheduler::Scheduler(SchedulerConfig config) : config_(config) {}

bool Scheduler::run(const StepFn& step, std::string& error) {
    return run_impl(step, nullptr, error);
}

bool Scheduler::run(const ExchangeFn& exchange, const StepFn& step,
                    std::string& error) {
    return run_impl(step, &exchange, error);
}

bool Scheduler::run_impl(const StepFn& step, const ExchangeFn* exchange,
                         std::string& error) {
    stats_ = SchedulerStats {};

    if (config_.step_size <= 0.0) {
        error = "scheduler step_size must be positive";
        return false;
    }
    if (!step) {
        error = "scheduler step function is empty";
        return false;
    }
    if (exchange != nullptr && !*exchange) {
        error = "scheduler exchange function is empty";
        return false;
    }

    const double step_size = config_.step_size;
    const double spin_margin_s =
        config_.spin_margin_s > 0.0
            ? (config_.spin_margin_s < step_size ? config_.spin_margin_s : step_size)
            : 0.0;
    const auto step_duration =
        std::chrono::duration_cast<Clock::duration>(Seconds(step_size));

    const Clock::time_point start = Clock::now();
    Clock::time_point deadline = start + step_duration;

    for (std::uint64_t index = 0; config_.max_steps == 0 || index < config_.max_steps;
         ++index) {
        const double simulation_time = static_cast<double>(index) * step_size;

        if (exchange != nullptr && !(*exchange)(simulation_time, step_size, error)) {
            return false;
        }

        ++stats_.steps;
        if (!step(simulation_time, step_size, error)) {
            return false;
        }

        if (!config_.realtime) {
            continue;
        }

        wait_until(deadline, spin_margin_s);

        const Clock::time_point now = Clock::now();
        if (now > deadline) {
            const double lateness_s =
                std::chrono::duration_cast<Seconds>(now - deadline).count();
            ++stats_.overruns;
            if (lateness_s > stats_.max_lateness_s) {
                stats_.max_lateness_s = lateness_s;
            }

            switch (config_.overrun_policy) {
                case OverrunPolicy::Warn:
                    deadline += step_duration;
                    break;
                case OverrunPolicy::Skip:
                    deadline = now + step_duration;
                    break;
                case OverrunPolicy::Fail:
                    error = "scheduler deadline missed by " + std::to_string(lateness_s) +
                            " s at step " + std::to_string(index);
                    return false;
            }
        } else {
            deadline += step_duration;
        }
    }

    return true;
}

const SchedulerStats& Scheduler::stats() const noexcept {
    return stats_;
}

}  // namespace pyfmi_interop
