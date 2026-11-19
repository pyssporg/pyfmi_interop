#include "pyfmi_interop/runtime/transport.hpp"

#include <memory>
#include <string>
#include <vector>

#include "pyfmi_interop/runtime/loopback_transport.hpp"

namespace pyfmi_interop {

const std::string* TransportConfig::find(const std::string& key) const {
    for (const auto& option : options) {
        if (option.first == key) {
            return &option.second;
        }
    }
    return nullptr;
}

std::unique_ptr<Transport> make_transport(const std::string& name, std::string& error) {
    if (name == "loopback") {
        return std::make_unique<LoopbackTransport>();
    }

    error = "unknown transport '" + name + "'; known transports: loopback";
    return nullptr;
}

std::vector<std::string> transport_names() {
    return {"loopback"};
}

bool transport_available(const std::string& name) {
    std::string error;
    const std::unique_ptr<Transport> transport = make_transport(name, error);
    return transport != nullptr && transport->available();
}

}  // namespace pyfmi_interop
