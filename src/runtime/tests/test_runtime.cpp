#include "pyfmi_interop/runtime/loopback_transport.hpp"
#include "pyfmi_interop/runtime/model_runtime.hpp"
#include "pyfmi_interop/runtime/scheduler.hpp"
#include "pyfmi_interop/runtime/transport.hpp"

#include <chrono>
#include <cstddef>
#include <optional>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

using namespace pyfmi_interop;

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

}  // namespace

int main() {
    // Value factories and assign_from.
    Value real = Value::make_real(2.5);
    if (real.type != DataType::Real || real.real_value != 2.5) {
        return fail("make_real");
    }
    Value integer = Value::make_integer(-7);
    if (integer.type != DataType::Integer || integer.integer_value != -7) {
        return fail("make_integer");
    }
    Value boolean = Value::make_boolean(true);
    if (boolean.type != DataType::Boolean || !boolean.boolean_value) {
        return fail("make_boolean");
    }
    Value text = Value::make_string("hello");
    if (text.type != DataType::String || text.string_value != "hello") {
        return fail("make_string");
    }
    if (Value::make_string(nullptr).string_value != "") {
        return fail("make_string(null)");
    }

    Value copied = Value::make_boolean(false);
    copied.assign_from(Value::make_boolean(true));
    if (copied.type != DataType::Boolean || !copied.boolean_value) {
        return fail("assign_from boolean");
    }
    Value keeps_type = Value::make_real(1.0);
    keeps_type.assign_from(Value::make_integer(9));
    if (keeps_type.type != DataType::Real || keeps_type.integer_value != 9) {
        return fail("assign_from must preserve the destination type");
    }
    Value string_copy = Value::make_string("");
    string_copy.assign_from(Value::make_string("payload"));
    if (string_copy.string_value != "payload") {
        return fail("assign_from string");
    }

    // Sample helpers.
    Sample sample;
    sample.resize(4);
    if (sample.values.size() != 4 || sample.valid.size() != 4) {
        return fail("Sample::resize");
    }
    if (sample.is_valid(0) || sample.is_valid(100)) {
        return fail("Sample::is_valid default/out-of-range");
    }
    sample.valid[1] = 1;
    if (!sample.is_valid(1)) {
        return fail("Sample::is_valid set");
    }
    sample.clear_valid();
    if (sample.is_valid(1)) {
        return fail("Sample::clear_valid");
    }

    // Loopback byte round trip and stale drop.
    LoopbackTransport loopback;
    loopback.initialize("loopback");
    const std::vector<std::byte> outbound{std::byte{0x01}, std::byte{0x02},
                                          std::byte{0x03}};
    if (!loopback.send(outbound)) {
        return fail("loopback send");
    }
    const std::optional<std::vector<std::byte>> inbound = loopback.receive();
    if (!inbound || *inbound != outbound) {
        return fail("loopback round-trip bytes");
    }
    if (!loopback.send(outbound) || !loopback.send(outbound) ||
        loopback.stats().dropped_stale != 1) {
        return fail("loopback stale frame accounting");
    }
    (void)loopback.receive();

    // Registry: unknown names throw with the available names.
    try {
        (void)make_transport("does-not-exist");
        return fail("unknown transport must throw");
    } catch (const TransportError& error) {
        const std::string message = error.what();
        if (message.find("unknown transport") == std::string::npos ||
            message.find("loopback") == std::string::npos) {
            return fail("unknown transport error text");
        }
    }
    const std::vector<std::string> names = transport_names();
    bool has_loopback = false;
    for (const std::string& name : names) {
        if (name == "loopback") {
            has_loopback = true;
        }
    }
    if (!has_loopback) {
        return fail("transport registry names");
    }

    // Scheduler: fixed step count without realtime pacing.
    SchedulerConfig scheduler_config;
    scheduler_config.step_size = 0.001;
    scheduler_config.realtime = false;
    scheduler_config.max_steps = 3;
    Scheduler scheduler(scheduler_config);
    std::uint64_t calls = 0;
    std::string scheduler_error;
    if (!scheduler.run(
            [&calls](double time, double step, std::string&) {
                ++calls;
                return time >= 0.0 && step > 0.0;
            },
            scheduler_error)) {
        return fail("scheduler fast run");
    }
    if (calls != 3 || scheduler.stats().steps != 3 || scheduler.stats().overruns != 0) {
        return fail("scheduler fast run statistics");
    }

    // Scheduler: exchange hook runs before each step.
    scheduler_config.max_steps = 3;
    Scheduler exchanging(scheduler_config);
    std::vector<int> order;
    std::string exchange_error;
    if (!exchanging.run(
            [&order](double, double, std::string&) {
                order.push_back(0);
                return true;
            },
            [&order](double, double, std::string&) {
                order.push_back(1);
                return true;
            },
            exchange_error)) {
        return fail("scheduler exchange run");
    }
    if (order != std::vector<int>({0, 1, 0, 1, 0, 1})) {
        return fail("scheduler must call exchange before every step");
    }

    // Scheduler: exchange failure stops the run with its error.
    Scheduler exchanging_abort(scheduler_config);
    exchange_error.clear();
    if (exchanging_abort.run(
            [](double, double, std::string& step_error) {
                step_error = "exchange stop";
                return false;
            },
            [](double, double, std::string&) { return true; },
            exchange_error)) {
        return fail("scheduler must abort when exchange returns false");
    }
    if (exchange_error != "exchange stop") {
        return fail("scheduler exchange error propagation");
    }

    // Scheduler: step function abort.
    scheduler_config.max_steps = 10;
    Scheduler aborting(scheduler_config);
    std::uint64_t abort_calls = 0;
    scheduler_error.clear();
    if (aborting.run(
            [&abort_calls](double, double, std::string& step_error) {
                ++abort_calls;
                if (abort_calls == 2) {
                    step_error = "intentional stop";
                    return false;
                }
                return true;
            },
            scheduler_error)) {
        return fail("scheduler must abort when the step function returns false");
    }
    if (scheduler_error != "intentional stop") {
        return fail("scheduler step error propagation");
    }

    // Scheduler: deliberate overrun under each policy.
    SchedulerConfig overrun_config;
    overrun_config.step_size = 0.001;
    overrun_config.realtime = true;
    overrun_config.max_steps = 2;

    for (const OverrunPolicy policy :
         {OverrunPolicy::Warn, OverrunPolicy::Skip, OverrunPolicy::Fail}) {
        overrun_config.overrun_policy = policy;
        Scheduler overrun_scheduler(overrun_config);
        std::string overrun_error;
        const bool ok = overrun_scheduler.run(
            [](double, double, std::string&) {
                std::this_thread::sleep_for(std::chrono::milliseconds(3));
                return true;
            },
            overrun_error);
        if (overrun_scheduler.stats().overruns == 0 ||
            overrun_scheduler.stats().max_lateness_s <= 0.0) {
            return fail("scheduler must count a deliberate overrun");
        }
        if (policy == OverrunPolicy::Fail) {
            if (ok || overrun_error.empty()) {
                return fail("scheduler Fail policy must stop with an error");
            }
        } else if (!ok || !overrun_error.empty()) {
            return fail("scheduler Warn/Skip policy must continue");
        }
    }

    // Invalid configuration.
    SchedulerConfig invalid;
    invalid.step_size = 0.0;
    Scheduler invalid_scheduler(invalid);
    scheduler_error.clear();
    if (invalid_scheduler.run([](double, double, std::string&) { return true; },
                              scheduler_error) ||
        scheduler_error.empty()) {
        return fail("scheduler must reject a non-positive step size");
    }

    return EXIT_SUCCESS;
}
