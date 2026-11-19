#include "pyfmi_interop/runtime/model_runtime.hpp"
#include "pyfmi_interop/runtime/transport.hpp"
#include "pyfmi_interop/runtime/wire.hpp"

#include "fmi2Functions.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <memory>
#include <new>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {

using pyfmi_interop::DataType;
using pyfmi_interop::Direction;
using pyfmi_interop::ModelRuntime;
using pyfmi_interop::Transport;
using pyfmi_interop::ByteSpan;
using pyfmi_interop::TransportError;
using pyfmi_interop::TransportRole;
using pyfmi_interop::Value;
using pyfmi_interop::WireModelCodec;
namespace wire = pyfmi_interop::wire;

// One fmi2Component.  The facade is synchronous: fmi2DoStep calls
// model->step() on the caller's thread and no background thread is created.
struct InstanceState {
    ModelRuntime* model = nullptr;
    std::unique_ptr<Transport> transport;
    WireModelCodec* codec = nullptr;
    TransportRole role = TransportRole::None;
    std::array<std::uint8_t, wire::kModelIdSize> model_id{};
    std::uint32_t instance_id = 0;
    std::uint64_t sequence = 0;
    std::uint64_t receive_misses = 0;
    std::string payload;
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
                      instance_name != nullptr ? instance_name : "pyfmi_interop",
                      fmi2Error, "error", "%s", message);
}

std::string environment_value(const char* name) {
    const char* value = std::getenv(name);
    return value != nullptr ? std::string(value) : std::string();
}

std::uint32_t instance_identity(const std::string& name) {
    std::uint32_t hash = 2166136261u;  // FNV-1a, stable across processes.
    for (const char character : name) {
        hash ^= static_cast<std::uint8_t>(character);
        hash *= 16777619u;
    }
    return hash == 0u ? 1u : hash;
}

bool declares_parameter_interface(const ModelRuntime* model) {
    if (model == nullptr) {
        return false;
    }
    for (const auto& signal : model->signals()) {
        if (signal.direction == Direction::Parameter) {
            return true;
        }
    }
    return false;
}

std::string parameter_text(const ModelRuntime* model, const char* key) {
    std::size_t length = 0;
    const char* value = model->interop_parameter_string(key, &length);
    return value != nullptr ? std::string(value, length) : std::string();
}

// `PYFMI_INTEROP_TRANSPORT` carries the full URI.  The legacy endpoint
// variable still supplies the authority for a bare scheme.  The default is
// loopback.  This channel is only consulted when the model declares no
// parameter interface at all; an authored interface is authoritative.
std::string resolve_environment_transport_uri(std::string& error) {
    std::string value = environment_value("PYFMI_INTEROP_TRANSPORT");
    const std::string endpoint = environment_value("PYFMI_INTEROP_TRANSPORT_ENDPOINT");
    if (value.empty()) {
        value = "loopback";
    }
    if (value == "none") {
        error = "a transport role requires PYFMI_INTEROP_TRANSPORT to name a backend";
        return {};
    }
    if (value.find("://") == std::string::npos && !endpoint.empty()) {
        value += "://" + endpoint;
    }
    return value;
}

// Parameter values are deployment configuration: `transport`, `bind_address`,
// `peer_address`, `queue_depth`, and `deadline_s` are the recognised keys.  A
// model with a parameter interface never reads the environment, so two
// instances in one process can bind different endpoints.
std::string resolve_transport_uri(const ModelRuntime* model, std::string& error) {
    if (!declares_parameter_interface(model)) {
        return resolve_environment_transport_uri(error);
    }

    const std::string scheme = parameter_text(model, "transport");
    const std::string bind = parameter_text(model, "bind_address");
    const std::string peer = parameter_text(model, "peer_address");

    if (scheme.empty() || scheme == "loopback") {
        return "loopback";
    }
    if (scheme != "udp" && scheme != "tcp") {
        error = "parameter 'transport' value '" + scheme +
                "' is not accepted; accepted values: loopback, udp, tcp";
        return {};
    }
    if (bind.empty()) {
        return "loopback";
    }

    std::string uri = scheme + "://" + bind;
    if (!peer.empty()) {
        uri += "?peer=" + peer;
    }
    return uri;
}

bool parameter_is_fixed(const InstanceState* instance,
                        fmi2ValueReference value_reference) {
    if (instance == nullptr || instance->model == nullptr) {
        return false;
    }
    for (const auto& signal : instance->model->signals()) {
        if (signal.value_reference != value_reference) {
            continue;
        }
        if (signal.direction != Direction::Parameter) {
            return false;
        }
        return instance->in_initialization_mode || instance->initialized ||
               instance->terminated;
    }
    return false;
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
        pyfmi_interop_destroy_model(instance->model);
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

    ModelRuntime* model = pyfmi_interop_create_model();
    if (model == nullptr) {
        log_instantiate_error(
            functions, instanceName,
            "pyfmi_interop: pyfmi_interop_create_model() returned nullptr; "
            "the model library was built without a generated model");
        return nullptr;
    }

    auto* instance = new (std::nothrow) InstanceState {};
    if (instance == nullptr) {
        pyfmi_interop_destroy_model(model);
        log_instantiate_error(functions, instanceName,
                              "pyfmi_interop: out of memory creating instance");
        return nullptr;
    }

    instance->model = model;
    instance->callbacks = *functions;
    instance->instance_name =
        instanceName != nullptr ? instanceName : "pyfmi_interop";
    instance->logging_on = loggingOn == fmi2True;
    instance->instance_id = instance_identity(instance->instance_name);

    // The generated model reports its role; a model without a codec keeps the
    // historical no-transport step exactly.
    instance->codec = model->wire_codec();
    if (instance->codec != nullptr) {
        instance->role = instance->codec->transport_role();
    }
    if (instance->role != TransportRole::None &&
        !instance->codec->wire_model_id(instance->model_id)) {
        return transport_instantiate_failure(
            instance, functions, instanceName,
            "pyfmi_interop: the model has a transport role but no wire model id");
    }

    // The transport is opened in fmi2EnterInitializationMode, after the master
    // has written the parameter values that configure it.

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
        pyfmi_interop_destroy_model(instance->model);
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

    if (instance->role != TransportRole::None) {
        if (instance->transport) {
            instance->transport->finalize();
            instance->transport.reset();
        }

        std::string uri_error;
        const std::string uri = resolve_transport_uri(instance->model, uri_error);
        if (uri.empty()) {
            return report_error(
                instance, "fmi2EnterInitializationMode: " +
                              (uri_error.empty()
                                   ? std::string("no transport URI configured")
                                   : uri_error));
        }

        try {
            std::unique_ptr<Transport> transport = pyfmi_interop::make_transport(uri);
            transport->initialize(uri);
            instance->transport = std::move(transport);
        } catch (const std::exception& error) {
            return report_error(instance, "fmi2EnterInitializationMode: transport '" +
                                              uri + "' failed: " + error.what());
        }
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
    instance->sequence = 0;
    instance->receive_misses = 0;
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
        if (parameter_is_fixed(instance, vr[index])) {
            return report_error(instance, "fmi2SetReal: parameter value reference " +
                                              std::to_string(vr[index]) +
                                              " is fixed after initialization");
        }
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
        if (parameter_is_fixed(instance, vr[index])) {
            return report_error(instance, "fmi2SetInteger: parameter value reference " +
                                              std::to_string(vr[index]) +
                                              " is fixed after initialization");
        }
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
        if (parameter_is_fixed(instance, vr[index])) {
            return report_error(instance, "fmi2SetBoolean: parameter value reference " +
                                              std::to_string(vr[index]) +
                                              " is fixed after initialization");
        }
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
        if (parameter_is_fixed(instance, vr[index])) {
            return report_error(instance, "fmi2SetString: parameter value reference " +
                                              std::to_string(vr[index]) +
                                              " is fixed after initialization");
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

    // Synchronous by design: no background thread and no step queue.  The
    // role decides whether a byte frame is received and/or sent around the
    // model step; `None` is exactly the historical step-only path.
    auto step_model = [&]() {
        instance->model->step(currentCommunicationPoint, communicationStepSize);
    };

    auto receive_and_apply = [&]() {
        if (instance->transport == nullptr || instance->codec == nullptr) {
            return;
        }
        std::optional<std::vector<std::byte>> frame;
        try {
            frame = instance->transport->receive();
        } catch (const std::exception& error) {
            instance->transport->record_format_error();
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "receive failed: " + std::string(error.what()));
            }
            ++instance->receive_misses;
            return;
        }
        if (!frame) {
            // No inbound frame: hold the previous input values.  They are
            // never cleared or replaced with NaN.
            ++instance->receive_misses;
            return;
        }

        const std::string_view buffer(reinterpret_cast<const char*>(frame->data()),
                                      frame->size());
        const wire::DecodeResult decoded = wire::decode_frame(buffer);
        if (!decoded) {
            if (decoded.error.code == wire::ErrorCode::HeaderChecksumError ||
                decoded.error.code == wire::ErrorCode::PayloadChecksumError) {
                instance->transport->record_crc_error();
            } else {
                instance->transport->record_format_error();
            }
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "dropped frame: " + decoded.error.message);
            }
            return;
        }
        if (decoded.frame.header.model_id != instance->model_id) {
            instance->transport->record_model_id_mismatch();
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "dropped frame: model id mismatch");
            }
            return;
        }
        if (decoded.frame.header.payload_format != instance->codec->payload_format()) {
            instance->transport->record_format_error();
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "dropped frame: payload format " +
                                std::string(wire::payload_format_name(
                                    decoded.frame.header.payload_format)) +
                                " does not match " +
                                wire::payload_format_name(instance->codec->payload_format()));
            }
            return;
        }

        const std::string_view payload(
            reinterpret_cast<const char*>(decoded.frame.payload.data()),
            decoded.frame.payload.size());
        std::string error;
        if (!instance->codec->decode_wire_payload(payload, error)) {
            instance->transport->record_format_error();
            if (instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "dropped payload: " + error);
            }
        }
    };

    auto publish_and_send = [&]() -> fmi2Status {
        if (instance->transport == nullptr || instance->codec == nullptr) {
            return fmi2OK;
        }
        instance->payload.clear();
        std::string error;
        if (!instance->codec->encode_wire_payload(instance->payload, error)) {
            return report_error(instance,
                                "fmi2DoStep: payload encode failed: " + error);
        }

        const double nanoseconds =
            currentCommunicationPoint > 0.0 ? currentCommunicationPoint * 1e9 : 0.0;
        const wire::EncodeResult encoded = wire::encode_frame(
            instance->model_id, instance->payload, instance->instance_id,
            instance->sequence + 1, static_cast<std::uint64_t>(nanoseconds),
            instance->codec->payload_format());
        if (!encoded) {
            return report_error(instance, "fmi2DoStep: frame encode failed: " +
                                              encoded.error.message);
        }
        ++instance->sequence;

        const ByteSpan bytes(
            reinterpret_cast<const std::byte*>(encoded.frame.data()),
            encoded.frame.size());
        try {
            if (!instance->transport->send(bytes) && instance->logging_on) {
                log_message(instance, fmi2Warning, "transport",
                            "send skipped: the transport would block");
            }
        } catch (const std::exception& send_error) {
            return report_error(instance, "fmi2DoStep: transport send failed: " +
                                              std::string(send_error.what()));
        }
        return fmi2OK;
    };

    switch (instance->role) {
        case TransportRole::None:
            step_model();
            break;
        case TransportRole::Sender:
            step_model();
            if (publish_and_send() != fmi2OK) {
                return fmi2Error;
            }
            break;
        case TransportRole::Receiver:
            receive_and_apply();
            step_model();
            break;
        case TransportRole::Adapter:
            receive_and_apply();
            step_model();
            if (publish_and_send() != fmi2OK) {
                return fmi2Error;
            }
            break;
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
