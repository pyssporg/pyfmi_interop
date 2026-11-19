#pragma once

#include <string>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {

// ASAM X-DCP (Distributed Co-Simulation Protocol) adapter.  Protocol traffic is
// delegated to DCPLib; this file only maps model signals.  See dcp.cpp.
class DcpTransport final : public Transport {
public:
    bool initialize(const TransportConfig& config, std::string& error) override;
    void finalize() noexcept override;
    bool available() const noexcept override;
    bool send(const Sample& sample, std::string& error) override;
    bool receive(Sample& sample, std::string& error) override;
};

}  // namespace pyfmi_interop
