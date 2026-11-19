#include "pyfmi_interop/runtime/model_runtime.hpp"
#include "pyfmi_interop/runtime/wire.hpp"

#include "fmi2Functions.h"

#include <array>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

namespace {

using pyfmi_interop::DataType;
using pyfmi_interop::Direction;
using pyfmi_interop::ModelRuntime;
using pyfmi_interop::Sample;
using pyfmi_interop::SignalDescriptor;
using pyfmi_interop::TransportRole;
using pyfmi_interop::Value;
using pyfmi_interop::WireModelCodec;

std::string g_last_log;

void logger(fmi2ComponentEnvironment, fmi2String, fmi2Status, fmi2String,
            fmi2String message, ...) {
    char buffer[512] = {0};
    va_list args;
    va_start(args, message);
    std::vsnprintf(buffer, sizeof(buffer), message != nullptr ? message : "", args);
    va_end(args);
    g_last_log = buffer;
}

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

void set_no_model(bool enabled) {
#if defined(_WIN32)
    _putenv_s("PYFMI_INTEROP_TEST_NO_MODEL", enabled ? "1" : "");
#else
    if (enabled) {
        setenv("PYFMI_INTEROP_TEST_NO_MODEL", "1", 1);
    } else {
        unsetenv("PYFMI_INTEROP_TEST_NO_MODEL");
    }
#endif
}

void set_role(const char* role) {
#if defined(_WIN32)
    _putenv_s("PYFMI_INTEROP_TEST_ROLE", role != nullptr ? role : "");
#else
    if (role != nullptr) {
        setenv("PYFMI_INTEROP_TEST_ROLE", role, 1);
    } else {
        unsetenv("PYFMI_INTEROP_TEST_ROLE");
    }
#endif
}

void set_transport(const char* name) {
#if defined(_WIN32)
    _putenv_s("PYFMI_INTEROP_TRANSPORT", name != nullptr ? name : "");
    _putenv_s("PYFMI_INTEROP_TRANSPORT_ENDPOINT", "");
    _putenv_s("PYFMI_INTEROP_TRANSPORT_TIMEOUT_MS", "");
#else
    if (name != nullptr) {
        setenv("PYFMI_INTEROP_TRANSPORT", name, 1);
    } else {
        unsetenv("PYFMI_INTEROP_TRANSPORT");
    }
    unsetenv("PYFMI_INTEROP_TRANSPORT_ENDPOINT");
    unsetenv("PYFMI_INTEROP_TRANSPORT_TIMEOUT_MS");
#endif
}

class TestModel final : public ModelRuntime, public WireModelCodec {
public:
    TestModel() {
        signals_ = {
            {"speed", 1, DataType::Real, Direction::Output, 0.0, 0},
            {"count", 2, DataType::Integer, Direction::Output, 0.0, 0},
            {"enabled", 3, DataType::Boolean, Direction::Output, 0.0, 0},
            {"mode", 4, DataType::String, Direction::Output, 0.0, 16},
            {"command", 5, DataType::Real, Direction::Input, 0.0, 0},
            {"setpoint", 6, DataType::Integer, Direction::Input, 0.0, 0},
        };
        reset();
    }

    const std::vector<SignalDescriptor>& signals() const override {
        return signals_;
    }

    void reset() override {
        speed_ = 1.5;
        count_ = 7;
        enabled_ = true;
        mode_ = "auto";
        command_ = 0.0;
        setpoint_ = 0;
        steps_ = 0;
        last_time_ = 0.0;
    }

    void step(double time, double step_size) override {
        last_time_ = time;
        ++steps_;
        speed_ += command_ * step_size;
        count_ += 1;
        enabled_ = !enabled_;
    }

    bool read(std::uint32_t value_reference, Value& out) const override {
        switch (value_reference) {
            case 1:
                out = Value::make_real(speed_);
                return true;
            case 2:
                out = Value::make_integer(count_);
                return true;
            case 3:
                out = Value::make_boolean(enabled_);
                return true;
            case 4:
                out = Value::make_string(mode_.c_str());
                return true;
            case 5:
                out = Value::make_real(command_);
                return true;
            case 6:
                out = Value::make_integer(setpoint_);
                return true;
            default:
                return false;
        }
    }

    bool write(std::uint32_t value_reference, const Value& value) override {
        switch (value_reference) {
            case 5:
                if (value.type != DataType::Real) {
                    return false;
                }
                command_ = value.real_value;
                return true;
            case 6:
                if (value.type != DataType::Integer) {
                    return false;
                }
                setpoint_ = value.integer_value;
                return true;
            default:
                return false;  // Outputs are not writable.
        }
    }

    void publish(Sample& sample) const override {
        if (sample.values.size() > 1) {
            sample.values[1] = Value::make_real(speed_);
            sample.valid[1] = 1;
        }
        // Feed the input back with an offset so the consume hook is observable.
        if (sample.values.size() > 5) {
            sample.values[5] = Value::make_real(command_ + 1.0);
            sample.valid[5] = 1;
        }
        sample.simulation_time = last_time_;
    }

    void consume(const Sample& sample) override {
        if (sample.values.size() > 5 && sample.is_valid(5) &&
            sample.values[5].type == DataType::Real) {
            command_ = sample.values[5].real_value;
        }
    }

    WireModelCodec* wire_codec() noexcept override { return this; }

    TransportRole transport_role() const override {
        const char* value = std::getenv("PYFMI_INTEROP_TEST_ROLE");
        if (value == nullptr) {
            return TransportRole::None;
        }
        const std::string role(value);
        if (role == "sender") {
            return TransportRole::Sender;
        }
        if (role == "receiver") {
            return TransportRole::Receiver;
        }
        if (role == "adapter") {
            return TransportRole::Adapter;
        }
        return TransportRole::None;
    }

    pyfmi_interop::wire::PayloadFormat payload_format() const override {
        return pyfmi_interop::wire::PayloadFormat::Opaque;
    }

    bool wire_model_id(
        std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize>& out) const override {
        std::vector<pyfmi_interop::wire::ModelIdSignal> records;
        records.reserve(signals_.size());
        for (const SignalDescriptor& signal : signals_) {
            records.push_back({signal.value_reference,
                               static_cast<std::uint8_t>(signal.type)});
        }
        out = pyfmi_interop::wire::model_id("test", 0.5, records);
        return true;
    }

    // The test payload is one little-endian double: the input is fed back with
    // an offset, which makes the round trip observable.
    bool encode_wire_payload(std::string& payload,
                             std::string& error) const override {
        (void)error;
        const double value = command_ + 1.0;
        payload.assign(reinterpret_cast<const char*>(&value), sizeof(value));
        return true;
    }

    bool decode_wire_payload(std::string_view payload,
                             std::string& error) override {
        if (payload.size() != sizeof(double)) {
            error = "test payload must be one double";
            return false;
        }
        std::memcpy(&command_, payload.data(), sizeof(command_));
        return true;
    }

private:
    std::vector<SignalDescriptor> signals_;
    double speed_ = 0.0;
    std::int32_t count_ = 0;
    bool enabled_ = false;
    std::string mode_;
    double command_ = 0.0;
    std::int32_t setpoint_ = 0;
    std::uint64_t steps_ = 0;
    double last_time_ = 0.0;
};

}  // namespace

// Strong test factory.  The shared facade carries a weak default; the test
// executable exports this definition (ENABLE_EXPORTS) so it wins at load time.
extern "C" pyfmi_interop::ModelRuntime* pyfmi_interop_create_model() {
    if (std::getenv("PYFMI_INTEROP_TEST_NO_MODEL") != nullptr) {
        return nullptr;
    }
    return new TestModel();
}

extern "C" void pyfmi_interop_destroy_model(pyfmi_interop::ModelRuntime* model) {
    delete model;
}

int main() {
    set_transport(nullptr);
    set_role(nullptr);

    fmi2CallbackFunctions callbacks {};
    callbacks.logger = logger;
    callbacks.allocateMemory = std::calloc;
    callbacks.freeMemory = std::free;

    // Factory returning nullptr must make fmi2Instantiate fail with a message.
    set_no_model(true);
    g_last_log.clear();
    fmi2Component component = fmi2Instantiate("no-model", fmi2CoSimulation, "guid",
                                              "file:///tmp", &callbacks, fmi2False,
                                              fmi2False);
    if (component != nullptr) {
        return fail("instantiate must fail when the factory returns nullptr");
    }
    if (g_last_log.find("returned nullptr") == std::string::npos) {
        return fail("instantiate failure must log a clear message");
    }
    set_no_model(false);

    // Type and callback validation.
    component = fmi2Instantiate("me", fmi2ModelExchange, "guid", "file:///tmp", &callbacks,
                                fmi2False, fmi2False);
    if (component != nullptr) {
        return fail("instantiate must reject fmi2ModelExchange");
    }
    component = fmi2Instantiate("no-callbacks", fmi2CoSimulation, "guid", "file:///tmp",
                                nullptr, fmi2False, fmi2False);
    if (component != nullptr) {
        return fail("instantiate must reject null callbacks");
    }

    component = fmi2Instantiate("model", fmi2CoSimulation, "guid", "file:///tmp", &callbacks,
                                fmi2False, fmi2False);
    if (component == nullptr) {
        return fail("instantiate must succeed with the test model factory");
    }

    if (std::string(fmi2GetTypesPlatform()) != "default" ||
        std::string(fmi2GetVersion()) != "2.0") {
        return fail("FMI version/platform strings");
    }
    if (fmi2SetDebugLogging(component, fmi2True, 0, nullptr) != fmi2OK) {
        return fail("setDebugLogging");
    }

    if (fmi2SetupExperiment(component, fmi2False, 0.0, 1.0, fmi2False, 0.0) != fmi2OK ||
        fmi2EnterInitializationMode(component) != fmi2OK ||
        fmi2ExitInitializationMode(component) != fmi2OK) {
        return fail("initialization sequence");
    }

    const fmi2ValueReference command_vr[] = {5};
    const fmi2Real command_value[] = {4.0};
    if (fmi2SetReal(component, command_vr, 1, command_value) != fmi2OK) {
        return fail("setReal input");
    }
    const fmi2ValueReference setpoint_vr[] = {6};
    const fmi2Integer setpoint_value[] = {11};
    if (fmi2SetInteger(component, setpoint_vr, 1, setpoint_value) != fmi2OK) {
        return fail("setInteger input");
    }

    const fmi2ValueReference speed_vr[] = {1};
    fmi2Real real_value[] = {0.0};
    if (fmi2GetReal(component, speed_vr, 1, real_value) != fmi2OK ||
        real_value[0] != 1.5) {
        return fail("getReal before step");
    }

    if (fmi2DoStep(component, 1.0, 0.5, fmi2True) != fmi2OK) {
        return fail("doStep");
    }
    if (fmi2GetReal(component, speed_vr, 1, real_value) != fmi2OK ||
        real_value[0] != 3.5) {
        return fail("doStep must call model->step()");
    }

    const fmi2ValueReference count_vr[] = {2};
    fmi2Integer integer_value[] = {0};
    if (fmi2GetInteger(component, count_vr, 1, integer_value) != fmi2OK ||
        integer_value[0] != 8) {
        return fail("getInteger after step");
    }

    const fmi2ValueReference enabled_vr[] = {3};
    fmi2Boolean boolean_value[] = {fmi2True};
    if (fmi2GetBoolean(component, enabled_vr, 1, boolean_value) != fmi2OK ||
        boolean_value[0] != fmi2False) {
        return fail("getBoolean after step");
    }

    const fmi2ValueReference mode_vr[] = {4};
    fmi2String string_value[] = {nullptr};
    if (fmi2GetString(component, mode_vr, 1, string_value) != fmi2OK ||
        std::string(string_value[0]) != "auto") {
        return fail("getString after step");
    }

    if (fmi2GetInteger(component, setpoint_vr, 1, integer_value) != fmi2OK ||
        integer_value[0] != 11) {
        return fail("getInteger input round-trip");
    }

    // Type and direction checks.
    if (fmi2GetReal(component, count_vr, 1, real_value) == fmi2OK) {
        return fail("getReal must reject an Integer reference");
    }
    if (fmi2SetReal(component, speed_vr, 1, command_value) == fmi2OK) {
        return fail("setReal must reject an output reference");
    }

    // Status and unsupported optional APIs.
    fmi2Status status = fmi2Error;
    if (fmi2GetStatus(component, fmi2DoStepStatus, &status) != fmi2OK ||
        status != fmi2OK) {
        return fail("getStatus DoStepStatus");
    }
    if (fmi2GetRealStatus(component, fmi2LastSuccessfulTime, real_value) != fmi2OK ||
        real_value[0] != 1.5) {
        return fail("getRealStatus LastSuccessfulTime");
    }
    if (fmi2GetBooleanStatus(component, fmi2Terminated, boolean_value) != fmi2OK ||
        boolean_value[0] != fmi2False) {
        return fail("getBooleanStatus Terminated before terminate");
    }
    fmi2FMUstate fmu_state = nullptr;
    if (fmi2GetFMUstate(component, &fmu_state) != fmi2Error || fmu_state != nullptr) {
        return fail("getFMUstate is expected to report fmi2Error in this runtime");
    }
    if (fmi2CancelStep(component) != fmi2Error) {
        return fail("cancelStep is expected to report fmi2Error");
    }

    if (fmi2Terminate(component) != fmi2OK) {
        return fail("terminate");
    }
    if (fmi2GetBooleanStatus(component, fmi2Terminated, boolean_value) != fmi2OK ||
        boolean_value[0] != fmi2True) {
        return fail("getBooleanStatus Terminated after terminate");
    }
    if (fmi2DoStep(component, 1.5, 0.5, fmi2True) != fmi2Error) {
        return fail("doStep after terminate must fail");
    }

    if (fmi2Reset(component) != fmi2OK) {
        return fail("reset");
    }
    if (fmi2DoStep(component, 0.0, 1.0, fmi2True) != fmi2Error) {
        return fail("doStep after reset must fail until initialization");
    }
    if (fmi2SetupExperiment(component, fmi2False, 0.0, 0.0, fmi2False, 0.0) != fmi2OK ||
        fmi2EnterInitializationMode(component) != fmi2OK ||
        fmi2ExitInitializationMode(component) != fmi2OK ||
        fmi2DoStep(component, 0.0, 1.0, fmi2True) != fmi2OK) {
        return fail("re-initialization after reset");
    }
    if (fmi2GetReal(component, speed_vr, 1, real_value) != fmi2OK ||
        real_value[0] != 1.5) {
        return fail("reset must restore the model state");
    }

    fmi2FreeInstance(component);

    // A role with an unknown backend must make instantiate fail clearly.
    set_role("adapter");
    set_transport("does-not-exist");
    g_last_log.clear();
    component = fmi2Instantiate("bad-transport", fmi2CoSimulation, "guid",
                                "file:///tmp", &callbacks, fmi2False, fmi2False);
    if (component != nullptr) {
        return fail("instantiate must fail for an unavailable transport");
    }
    if (g_last_log.find("unknown transport") == std::string::npos) {
        return fail("unavailable transport failure must log a clear message");
    }

    // Role-aware stepping: adapter does receive -> apply -> step -> publish ->
    // send around a loopback byte transport.  The first step has no inbound
    // frame and must hold its input value; the second consumes the published
    // frame.
    set_transport("loopback");
    g_last_log.clear();
    component = fmi2Instantiate("loopback", fmi2CoSimulation, "guid",
                                "file:///tmp", &callbacks, fmi2False, fmi2False);
    if (component == nullptr) {
        return fail("instantiate must accept the loopback transport");
    }
    if (fmi2SetupExperiment(component, fmi2False, 0.0, 0.0, fmi2False, 0.0) != fmi2OK ||
        fmi2EnterInitializationMode(component) != fmi2OK ||
        fmi2ExitInitializationMode(component) != fmi2OK) {
        return fail("loopback initialization sequence");
    }
    if (fmi2SetReal(component, command_vr, 1, command_value) != fmi2OK) {
        return fail("loopback setReal input");
    }
    if (fmi2DoStep(component, 0.0, 0.5, fmi2True) != fmi2OK ||
        fmi2GetReal(component, speed_vr, 1, real_value) != fmi2OK ||
        real_value[0] != 3.5) {
        return fail("loopback first step");
    }
    // The published frame feeds back into the input before the second step.
    if (fmi2DoStep(component, 0.5, 0.5, fmi2True) != fmi2OK ||
        fmi2GetReal(component, speed_vr, 1, real_value) != fmi2OK ||
        real_value[0] != 6.0) {
        return fail("loopback exchange must apply the received payload");
    }
    fmi2FreeInstance(component);
    set_transport(nullptr);
    set_role(nullptr);

    fmi2FreeInstance(nullptr);

    return EXIT_SUCCESS;
}
