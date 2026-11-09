#include "pyfmi_distributed/runtime/transport.hpp"

#include <memory>
#include <string>
#include <vector>

#include "pyfmi_distributed/runtime/adapters/dcp.hpp"
#include "pyfmi_distributed/runtime/adapters/dis.hpp"
#include "pyfmi_distributed/runtime/adapters/ed247.hpp"
#include "pyfmi_distributed/runtime/adapters/hla.hpp"
#include "pyfmi_distributed/runtime/adapters/ros2.hpp"
#include "pyfmi_distributed/runtime/loopback_transport.hpp"

namespace pyfmi_distributed {

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
    if (name == "hla") {
        return std::make_unique<HlaTransport>();
    }
    if (name == "dis") {
        return std::make_unique<DisTransport>();
    }
    if (name == "dcp") {
        return std::make_unique<DcpTransport>();
    }
    if (name == "ros2") {
        return std::make_unique<Ros2Transport>();
    }
    if (name == "ed247") {
        return std::make_unique<Ed247Transport>();
    }

    error = "unknown transport '" + name +
            "'; known transports: loopback, hla, dis, dcp, ros2, ed247";
    return nullptr;
}

std::vector<std::string> transport_names() {
    return {"loopback", "hla", "dis", "dcp", "ros2", "ed247"};
}

bool transport_available(const std::string& name) {
    std::string error;
    const std::unique_ptr<Transport> transport = make_transport(name, error);
    return transport != nullptr && transport->available();
}

}  // namespace pyfmi_distributed
