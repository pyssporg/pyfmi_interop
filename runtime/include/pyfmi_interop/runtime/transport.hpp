#pragma once

#include <memory>
#include <string>
#include <vector>

#include "pyfmi_interop/runtime/model_runtime.hpp"

namespace pyfmi_interop {

// Configuration is passed to initialize() and may allocate.  Nothing inside
// the step loop is allowed to build one of these.
struct TransportConfig {
    std::string name;
    std::string endpoint;
    double timeout_s = 0.0;
    // Ordered key/value options so generated and hand-written configs are
    // deterministic.
    std::vector<std::pair<std::string, std::string>> options;

    const std::string* find(const std::string& key) const;
};

// Preallocated frame.  See `Sample` in model_runtime.hpp; the transport only
// reads and writes existing storage.
class Transport {
public:
    virtual ~Transport() = default;

    // Called once before the first step.  Returns false and fills `error` when
    // the backend is unavailable or the configuration is rejected.
    virtual bool initialize(const TransportConfig& config, std::string& error) = 0;

    // Called once during shutdown.  Must not throw.
    virtual void finalize() noexcept = 0;

    // True when the backend was compiled in and its SDK initialized.  A stub
    // build always returns false.
    virtual bool available() const noexcept = 0;

    // Exchange one frame.  The realtime fast path must not allocate; a backend
    // that needs queues or serialization buffers allocates them in initialize().
    virtual bool send(const Sample& sample, std::string& error) = 0;
    virtual bool receive(Sample& sample, std::string& error) = 0;
};

// Transport registry.  Unknown names return nullptr and fill `error` with the
// list of known transports.
std::unique_ptr<Transport> make_transport(const std::string& name, std::string& error);

std::vector<std::string> transport_names();
bool transport_available(const std::string& name);

}  // namespace pyfmi_interop
