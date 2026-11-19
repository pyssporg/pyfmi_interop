#include "pyfmi_interop/runtime/adapters/dcp.hpp"
#include "pyfmi_interop/runtime/adapters/dis.hpp"
#include "pyfmi_interop/runtime/adapters/ed247.hpp"
#include "pyfmi_interop/runtime/adapters/hla.hpp"
#include "pyfmi_interop/runtime/adapters/ros2.hpp"
#include "pyfmi_interop/runtime/loopback_transport.hpp"
#include "pyfmi_interop/runtime/model_runtime.hpp"
#include "pyfmi_interop/runtime/scheduler.hpp"
#include "pyfmi_interop/runtime/transport.hpp"

#include <chrono>
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

bool check_adapter_stub(Transport& transport) {
    TransportConfig config;
    config.name = "stub";
    std::string error;
    if (transport.available()) {
        return false;
    }
    if (transport.initialize(config, error)) {
        return false;
    }
    return !error.empty();
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

    // Loopback round trip.
    LoopbackTransport loopback;
    TransportConfig loopback_config;
    loopback_config.name = "loopback";
    loopback_config.options.emplace_back("signal_count", "4");
    std::string error;
    if (!loopback.initialize(loopback_config, error)) {
        return fail("loopback initialize");
    }
    if (!loopback.available()) {
        return fail("loopback available");
    }

    Sample outbound;
    outbound.resize(4);
    outbound.simulation_time = 1.25;
    outbound.values[0] = Value::make_real(3.0);
    outbound.values[1] = Value::make_integer(5);
    outbound.values[2] = Value::make_boolean(true);
    outbound.values[3] = Value::make_string("loop");
    outbound.valid[0] = 1;
    outbound.valid[1] = 1;
    outbound.valid[2] = 1;
    outbound.valid[3] = 1;
    if (!loopback.send(outbound, error)) {
        return fail("loopback send");
    }

    Sample inbound;
    inbound.resize(4);
    if (!loopback.receive(inbound, error)) {
        return fail("loopback receive");
    }
    if (inbound.simulation_time != 1.25 || !inbound.is_valid(3) ||
        inbound.values[0].real_value != 3.0 ||
        inbound.values[1].integer_value != 5 ||
        !inbound.values[2].boolean_value ||
        inbound.values[3].string_value != "loop") {
        return fail("loopback round-trip payload");
    }

    // Registry.
    std::string registry_error;
    if (make_transport("does-not-exist", registry_error) != nullptr) {
        return fail("unknown transport must return nullptr");
    }
    if (registry_error.find("unknown transport") == std::string::npos ||
        registry_error.find("loopback") == std::string::npos) {
        return fail("unknown transport error text");
    }
    const std::vector<std::string> names = transport_names();
    bool has_loopback = false;
    for (const std::string& name : names) {
        if (name == "loopback") {
            has_loopback = true;
        }
    }
    if (!has_loopback || !transport_available("loopback") ||
        transport_available("does-not-exist")) {
        return fail("transport registry queries");
    }

    // Adapter stubs never act as available transports in this build.
    HlaTransport hla;
    DisTransport dis;
    DcpTransport dcp;
    Ros2Transport ros2;
    Ed247Transport ed247;
    if (!check_adapter_stub(hla) || !check_adapter_stub(dis) || !check_adapter_stub(dcp) ||
        !check_adapter_stub(ros2) || !check_adapter_stub(ed247)) {
        return fail("adapter stub must be unavailable with an explanatory error");
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
