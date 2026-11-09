#include "pyfmi_distributed/runtime/model_runtime.hpp"
#include "pyfmi_distributed/runtime/transport.hpp"

#include "fmi2Functions.h"

#include <cstddef>
#include <cstdlib>
#include <memory>
#include <new>
#include <string>
#include <vector>

namespace {

using pyfmi_distributed::DataType;
using pyfmi_distributed::ModelRuntime;
using pyfmi_distributed::Sample;
using pyfmi_distributed::Transport;
using pyfmi_distributed::TransportConfig;
using pyfmi_distributed::Value;

// One fmi2Component.  The facade is synchronous: fmi2DoStep calls
// model->step() on the caller's thread and no background thread is created.
struct InstanceState {
    ModelRuntime* model = nullptr;
    std::unique_ptr<Transport> transport;
    Sample sample;
    fmi2CallbackFunctions callbacks {};
    std::string instance_name;
    bool logging_on = false;
    bool in_initialization_mode = false;
    bool initialized = false;
    bool terminated = false;
    bool stop_time_defined = false;
    double start_time = 0.0;
    double stop_time = 0.0;
    double current_time = 0.0;
    double last_successful_time = 0.0;
    // Backing storage for fmi2GetString results.  FMI 2.0 keeps the returned
    // pointers valid until the next call to the same getter.
    std::vector<std::string> string_scratch;
};

InstanceState* as_instance(fmi2Component component) {
    return static_cast<InstanceState*>(component);
}

void log_message(InstanceState* instance, fmi2Status status, const char* category,
                 const std::string& message) {
    if (instance == nullptr || instance->callbacks.logger == nullptr) {
        return;
    }
    instance->callbacks.logger(instance->callbacks.componentEnvironment,
                               instance->instance_name.c_str(), status, category,
                               "%s", message.c_str());
}

fmi2Status report_error(InstanceState* instance, const std::string& message) {
    log_message(instance, fmi2Error, "error", message);
    return fmi2Error;
}

void log_instantiate_error(const fmi2CallbackFunctions* functions,
                           fmi2String instance_name, const char* message) {
    if (functions == nullptr || functions->logger == nullptr) {
        return;
    }
    functions->logger(functions->componentEnvironment,
                      instance_name != nullptr ? instance_name : "pyfmi_distributed",
                      fmi2Error, "error", "%s", message);
}

std::string environment_value(const char* name) {
    const char* value = std::getenv(name);
    return value != nullptr ? std::string(value) : std::string();
}

std::size_t sample_size(const ModelRuntime& model) {
    std::uint32_t maximum = 0;
    bool any = false;
    for (const auto& signal : model.signals()) {
        any = true;
        if (signal.value_reference > maximum) {
            maximum = signal.value_reference;
        }
    }
    return any ? static_cast<std::size_t>(maximum) + 1u : 0u;
}

fmi2Component transport_instantiate_failure(InstanceState* instance,
                                            const fmi2CallbackFunctions* functions,
                                            fmi2String instance_name,
                                            const std::string& message) {
    if (instance->transport) {
        instance->transport->finalize();
        instance->transport.reset();
    }
    if (instance->model != nullptr) {
        pyfmi_distributed_destroy_model(instance->model);
        instance->model = nullptr;
    }
    delete instance;
    log_instantiate_error(functions, instance_name, message.c_str());
    return nullptr;
}

const char* type_name(DataType type) {
    switch (type) {
        case DataType::Real:
            return "Real";
        case DataType::Integer:
            return "Integer";
        case DataType::Boolean:
            return "Boolean";
        case DataType::String:
            return "String";
    }
    return "unknown";
}

}  // namespace

extern "C" {

const char* fmi2GetTypesPlatform(void) {
    return fmi2TypesPlatform;
}

const char* fmi2GetVersion(void) {
    return fmi2Version;
}

fmi2Status fmi2SetDebugLogging(fmi2Component c, fmi2Boolean loggingOn, size_t,
                               const fmi2String[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->logging_on = loggingOn == fmi2True;
    return fmi2OK;
}

fmi2Component fmi2Instantiate(fmi2String instanceName, fmi2Type fmuType,
                              fmi2String, fmi2String fmuResourceLocation,
                              const fmi2CallbackFunctions* functions,
                              fmi2Boolean, fmi2Boolean loggingOn) {
    (void)fmuResourceLocation;

    if (fmuType != fmi2CoSimulation) {
        log_instantiate_error(functions, instanceName,
                              "fmi2Instantiate: only fmi2CoSimulation is supported");
        return nullptr;
    }
    if (functions == nullptr) {
        return nullptr;
    }

    ModelRuntime* model = pyfmi_distributed_create_model();
    if (model == nullptr) {
        log_instantiate_error(
            functions, instanceName,
            "pyfmi_distributed: pyfmi_distributed_create_model() returned nullptr; "
            "the model library was built without a generated model");
        return nullptr;
    }

    auto* instance = new (std::nothrow) InstanceState {};
    if (instance == nullptr) {
        pyfmi_distributed_destroy_model(model);
        log_instantiate_error(functions, instanceName,
                              "pyfmi_distributed: out of memory creating instance");
        return nullptr;
    }

    instance->model = model;
    instance->callbacks = *functions;
    instance->instance_name =
        instanceName != nullptr ? instanceName : "pyfmi_distributed";
    instance->logging_on = loggingOn == fmi2True;

    const std::string transport_name = environment_value("PYFMI_DIST_TRANSPORT");
    if (!transport_name.empty() && transport_name != "none") {
        TransportConfig config;
        config.name = transport_name;
        config.endpoint = environment_value("PYFMI_DIST_TRANSPORT_ENDPOINT");

        const std::string timeout_text =
            environment_value("PYFMI_DIST_TRANSPORT_TIMEOUT_MS");
        if (!timeout_text.empty()) {
            char* end = nullptr;
            const double timeout_ms = std::strtod(timeout_text.c_str(), &end);
            if (end == timeout_text.c_str() || *end != '\0' || timeout_ms < 0.0) {
                return transport_instantiate_failure(
                    instance, functions, instanceName,
                    "pyfmi_distributed: PYFMI_DIST_TRANSPORT_TIMEOUT_MS must be a "
                    "non-negative number");
            }
            config.timeout_s = timeout_ms / 1000.0;
        }

        const std::size_t signal_count = sample_size(*model);
        instance->sample.resize(signal_count);
        config.options.emplace_back("signal_count", std::to_string(signal_count));

        std::string transport_error;
        std::unique_ptr<Transport> transport =
            pyfmi_distributed::make_transport(transport_name, transport_error);
        if (transport == nullptr) {
            return transport_instantiate_failure(
                instance, functions, instanceName,
                "pyfmi_distributed: " + transport_error);
        }
        if (!transport->initialize(config, transport_error)) {
            return transport_instantiate_failure(
                instance, functions, instanceName,
                "pyfmi_distributed: transport '" + transport_name +
                    "' failed to initialize: " + transport_error);
        }
        if (!transport->available()) {
            transport->finalize();
            return transport_instantiate_failure(
                instance, functions, instanceName,
                "pyfmi_distributed: transport '" + transport_name +
                    "' is not available in this build");
        }
        instance->transport = std::move(transport);
    }

    return instance;
}

void fmi2FreeInstance(fmi2Component c) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return;
    }
    if (instance->transport) {
        instance->transport->finalize();
        instance->transport.reset();
    }
    if (instance->model != nullptr) {
        pyfmi_distributed_destroy_model(instance->model);
        instance->model = nullptr;
    }
    delete instance;
}

fmi2Status fmi2SetupExperiment(fmi2Component c, fmi2Boolean toleranceDefined,
                               fmi2Real tolerance, fmi2Real startTime,
                               fmi2Boolean stopTimeDefined, fmi2Real stopTime) {
    (void)toleranceDefined;
    (void)tolerance;

    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->start_time = startTime;
    instance->current_time = startTime;
    instance->last_successful_time = startTime;
    instance->stop_time_defined = stopTimeDefined == fmi2True;
    instance->stop_time = stopTime;
    return fmi2OK;
}

fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->in_initialization_mode = true;
    instance->current_time = instance->start_time;
    return fmi2OK;
}

fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->in_initialization_mode = false;
    instance->initialized = true;
    instance->terminated = false;
    instance->last_successful_time = instance->current_time;
    return fmi2OK;
}

fmi2Status fmi2Terminate(fmi2Component c) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->terminated = true;
    instance->initialized = false;
    return fmi2OK;
}

fmi2Status fmi2Reset(fmi2Component c) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->model->reset();
    instance->sample.clear_valid();
    instance->in_initialization_mode = false;
    instance->initialized = false;
    instance->terminated = false;
    instance->stop_time_defined = false;
    instance->start_time = 0.0;
    instance->current_time = 0.0;
    instance->last_successful_time = 0.0;
    return fmi2OK;
}

fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                       fmi2Real value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2GetReal: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        Value result;
        if (!instance->model->read(vr[index], result)) {
            return report_error(instance, "fmi2GetReal: unknown value reference " +
                                              std::to_string(vr[index]));
        }
        if (result.type != DataType::Real) {
            return report_error(instance,
                                "fmi2GetReal: value reference " +
                                    std::to_string(vr[index]) + " is " +
                                    type_name(result.type) + ", not Real");
        }
        value[index] = result.real_value;
    }
    return fmi2OK;
}

fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                          fmi2Integer value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2GetInteger: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        Value result;
        if (!instance->model->read(vr[index], result)) {
            return report_error(instance, "fmi2GetInteger: unknown value reference " +
                                              std::to_string(vr[index]));
        }
        if (result.type != DataType::Integer) {
            return report_error(instance,
                                "fmi2GetInteger: value reference " +
                                    std::to_string(vr[index]) + " is " +
                                    type_name(result.type) + ", not Integer");
        }
        value[index] = static_cast<fmi2Integer>(result.integer_value);
    }
    return fmi2OK;
}

fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                          fmi2Boolean value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2GetBoolean: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        Value result;
        if (!instance->model->read(vr[index], result)) {
            return report_error(instance, "fmi2GetBoolean: unknown value reference " +
                                              std::to_string(vr[index]));
        }
        if (result.type != DataType::Boolean) {
            return report_error(instance,
                                "fmi2GetBoolean: value reference " +
                                    std::to_string(vr[index]) + " is " +
                                    type_name(result.type) + ", not Boolean");
        }
        value[index] = result.boolean_value ? fmi2True : fmi2False;
    }
    return fmi2OK;
}

fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                         fmi2String value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2GetString: null argument");
    }

    instance->string_scratch.resize(nvr);
    for (size_t index = 0; index < nvr; ++index) {
        Value result;
        if (!instance->model->read(vr[index], result)) {
            return report_error(instance, "fmi2GetString: unknown value reference " +
                                              std::to_string(vr[index]));
        }
        if (result.type != DataType::String) {
            return report_error(instance,
                                "fmi2GetString: value reference " +
                                    std::to_string(vr[index]) + " is " +
                                    type_name(result.type) + ", not String");
        }
        instance->string_scratch[index] = result.string_value;
        value[index] = instance->string_scratch[index].c_str();
    }
    return fmi2OK;
}

fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                       const fmi2Real value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2SetReal: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        if (!instance->model->write(vr[index], Value::make_real(value[index]))) {
            return report_error(instance, "fmi2SetReal: value reference " +
                                              std::to_string(vr[index]) +
                                              " cannot be written");
        }
    }
    return fmi2OK;
}

fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                          const fmi2Integer value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2SetInteger: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        if (!instance->model->write(
                vr[index], Value::make_integer(static_cast<std::int32_t>(value[index])))) {
            return report_error(instance, "fmi2SetInteger: value reference " +
                                              std::to_string(vr[index]) +
                                              " cannot be written");
        }
    }
    return fmi2OK;
}

fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                          const fmi2Boolean value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2SetBoolean: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        if (!instance->model->write(vr[index],
                                    Value::make_boolean(value[index] == fmi2True))) {
            return report_error(instance, "fmi2SetBoolean: value reference " +
                                              std::to_string(vr[index]) +
                                              " cannot be written");
        }
    }
    return fmi2OK;
}

fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                         const fmi2String value[]) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || vr == nullptr || value == nullptr) {
        return report_error(instance, "fmi2SetString: null argument");
    }

    for (size_t index = 0; index < nvr; ++index) {
        if (value[index] == nullptr) {
            return report_error(instance, "fmi2SetString: null string at index " +
                                              std::to_string(index));
        }
        if (!instance->model->write(vr[index], Value::make_string(value[index]))) {
            return report_error(instance, "fmi2SetString: value reference " +
                                              std::to_string(vr[index]) +
                                              " cannot be written");
        }
    }
    return fmi2OK;
}

fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* FMUstate) {
    if (FMUstate != nullptr) {
        *FMUstate = nullptr;
    }
    return report_error(as_instance(c),
                        "fmi2GetFMUstate: FMU state serialization is not implemented "
                        "by the reusable runtime");
}

fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate) {
    return report_error(as_instance(c),
                        "fmi2SetFMUstate: FMU state serialization is not implemented "
                        "by the reusable runtime");
}

fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate*) {
    return report_error(as_instance(c),
                        "fmi2FreeFMUstate: FMU state serialization is not implemented "
                        "by the reusable runtime");
}

fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate, size_t*) {
    return report_error(as_instance(c),
                        "fmi2SerializedFMUstateSize: FMU state serialization is not "
                        "implemented by the reusable runtime");
}

fmi2Status fmi2SerializeFMUstate(fmi2Component c, fmi2FMUstate, fmi2Byte[], size_t) {
    return report_error(as_instance(c),
                        "fmi2SerializeFMUstate: FMU state serialization is not "
                        "implemented by the reusable runtime");
}

fmi2Status fmi2DeSerializeFMUstate(fmi2Component c, const fmi2Byte[], size_t,
                                   fmi2FMUstate*) {
    return report_error(as_instance(c),
                        "fmi2DeSerializeFMUstate: FMU state serialization is not "
                        "implemented by the reusable runtime");
}

fmi2Status fmi2GetDirectionalDerivative(fmi2Component c,
                                        const fmi2ValueReference[], size_t,
                                        const fmi2ValueReference[], size_t,
                                        const fmi2Real[], fmi2Real[]) {
    return report_error(as_instance(c),
                        "fmi2GetDirectionalDerivative: directional derivatives are not "
                        "available for a distributed CoSimulation model");
}

fmi2Status fmi2EnterEventMode(fmi2Component c) {
    return report_error(as_instance(c),
                        "fmi2EnterEventMode: Model Exchange API is not available in the "
                        "CoSimulation facade");
}

fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo* eventInfo) {
    if (eventInfo != nullptr) {
        *eventInfo = fmi2EventInfo {};
    }
    return report_error(as_instance(c),
                        "fmi2NewDiscreteStates: Model Exchange API is not available in "
                        "the CoSimulation facade");
}

fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c) {
    return report_error(as_instance(c),
                        "fmi2EnterContinuousTimeMode: Model Exchange API is not "
                        "available in the CoSimulation facade");
}

fmi2Status fmi2CompletedIntegratorStep(fmi2Component c, fmi2Boolean, fmi2Boolean* enterEventMode,
                                       fmi2Boolean* terminateSimulation) {
    if (enterEventMode != nullptr) {
        *enterEventMode = fmi2False;
    }
    if (terminateSimulation != nullptr) {
        *terminateSimulation = fmi2False;
    }
    return report_error(as_instance(c),
                        "fmi2CompletedIntegratorStep: Model Exchange API is not "
                        "available in the CoSimulation facade");
}

fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    instance->current_time = time;
    return fmi2OK;
}

fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real[], size_t) {
    return report_error(as_instance(c),
                        "fmi2SetContinuousStates: Model Exchange API is not available "
                        "in the CoSimulation facade");
}

fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real[], size_t) {
    return report_error(as_instance(c),
                        "fmi2GetDerivatives: Model Exchange API is not available in "
                        "the CoSimulation facade");
}

fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real[], size_t) {
    return report_error(as_instance(c),
                        "fmi2GetEventIndicators: Model Exchange API is not available "
                        "in the CoSimulation facade");
}

fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real[], size_t) {
    return report_error(as_instance(c),
                        "fmi2GetContinuousStates: Model Exchange API is not available "
                        "in the CoSimulation facade");
}

fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real[], size_t) {
    return report_error(as_instance(c),
                        "fmi2GetNominalsOfContinuousStates: Model Exchange API is not "
                        "available in the CoSimulation facade");
}

fmi2Status fmi2SetRealInputDerivatives(fmi2Component c, const fmi2ValueReference[],
                                       size_t, const fmi2Integer[],
                                       const fmi2Real[]) {
    return report_error(as_instance(c),
                        "fmi2SetRealInputDerivatives: input derivatives are not "
                        "supported by the reusable runtime");
}

fmi2Status fmi2GetRealOutputDerivatives(fmi2Component c, const fmi2ValueReference[],
                                        size_t, const fmi2Integer[], fmi2Real[]) {
    return report_error(as_instance(c),
                        "fmi2GetRealOutputDerivatives: output derivatives are not "
                        "supported by the reusable runtime");
}

fmi2Status fmi2DoStep(fmi2Component c, fmi2Real currentCommunicationPoint,
                      fmi2Real communicationStepSize, fmi2Boolean) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr) {
        return fmi2Error;
    }
    if (!instance->initialized || instance->terminated) {
        return report_error(instance,
                            "fmi2DoStep: the instance is not in continuous-time "
                            "CoSimulation mode");
    }
    if (communicationStepSize < 0.0) {
        return report_error(instance, "fmi2DoStep: negative communication step size");
    }

    // Synchronous by design: no background thread and no step queue.  With a
    // transport the frame is exchanged around the step; without one the model
    // runs exactly as before.
    if (instance->transport) {
        std::string transport_error;
        if (!instance->transport->receive(instance->sample, transport_error)) {
            // A transport may have no inbound frame for this step (the first
            // loopback step is the common case).  Run with a cleared frame
            // instead of failing the step.
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "receive returned no frame: " + transport_error);
            }
            instance->sample.clear_valid();
        }

        instance->model->consume(instance->sample);
        instance->model->step(currentCommunicationPoint, communicationStepSize);
        instance->sample.clear_valid();
        instance->model->publish(instance->sample);
        if (!instance->transport->send(instance->sample, transport_error)) {
            return report_error(instance, "fmi2DoStep: transport send failed: " +
                                              transport_error);
        }
    } else {
        instance->model->step(currentCommunicationPoint, communicationStepSize);
    }

    instance->current_time = currentCommunicationPoint + communicationStepSize;
    instance->last_successful_time = instance->current_time;
    return fmi2OK;
}

fmi2Status fmi2CancelStep(fmi2Component c) {
    return report_error(as_instance(c),
                        "fmi2CancelStep: the facade is synchronous, so no step can be "
                        "pending");
}

fmi2Status fmi2GetStatus(fmi2Component c, const fmi2StatusKind statusKind,
                         fmi2Status* value) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Error;
    }

    if (statusKind == fmi2DoStepStatus) {
        *value = fmi2OK;
        return fmi2OK;
    }
    if (statusKind == fmi2PendingStatus) {
        *value = fmi2Discard;  // Never pending: fmi2DoStep is synchronous.
        return fmi2OK;
    }
    return report_error(instance, "fmi2GetStatus: unsupported status kind");
}

fmi2Status fmi2GetRealStatus(fmi2Component c, const fmi2StatusKind statusKind,
                             fmi2Real* value) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Error;
    }

    if (statusKind == fmi2LastSuccessfulTime) {
        *value = instance->last_successful_time;
        return fmi2OK;
    }
    return report_error(instance, "fmi2GetRealStatus: unsupported status kind");
}

fmi2Status fmi2GetIntegerStatus(fmi2Component c, const fmi2StatusKind, fmi2Integer*) {
    return report_error(as_instance(c),
                        "fmi2GetIntegerStatus: no integer status is defined");
}

fmi2Status fmi2GetBooleanStatus(fmi2Component c, const fmi2StatusKind statusKind,
                                fmi2Boolean* value) {
    InstanceState* instance = as_instance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Error;
    }

    if (statusKind == fmi2Terminated) {
        *value = instance->terminated ? fmi2True : fmi2False;
        return fmi2OK;
    }
    return report_error(instance, "fmi2GetBooleanStatus: unsupported status kind");
}

fmi2Status fmi2GetStringStatus(fmi2Component c, const fmi2StatusKind, fmi2String*) {
    return report_error(as_instance(c),
                        "fmi2GetStringStatus: no string status is defined");
}

}  // extern "C"
