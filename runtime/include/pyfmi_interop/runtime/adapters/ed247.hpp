#pragma once

#include <string>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {

// ED-247 (ARINC 664) adapter.  Compile-gated stub: see ed247.cpp.
class Ed247Transport final : public Transport {
public:
    bool initialize(const TransportConfig& config, std::string& error) override;
    void finalize() noexcept override;
    bool available() const noexcept override;
    bool send(const Sample& sample, std::string& error) override;
    bool receive(Sample& sample, std::string& error) override;
};

}  // namespace pyfmi_interop
