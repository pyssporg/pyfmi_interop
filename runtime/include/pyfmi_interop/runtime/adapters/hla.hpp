#pragma once

#include <string>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {

// IEEE 1516 HLA federation adapter.  Compile-gated stub: see hla.cpp.
class HlaTransport final : public Transport {
public:
    bool initialize(const TransportConfig& config, std::string& error) override;
    void finalize() noexcept override;
    bool available() const noexcept override;
    bool send(const Sample& sample, std::string& error) override;
    bool receive(Sample& sample, std::string& error) override;
};

}  // namespace pyfmi_interop
