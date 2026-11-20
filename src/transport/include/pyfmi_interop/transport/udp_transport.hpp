#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {
namespace transport {

// One datagram is one wire frame.  Frames larger than 65507 bytes are
// rejected with TransportError; receive drains the socket and keeps the
// newest datagram.
class UdpTransport final : public Transport {
public:
    UdpTransport();
    ~UdpTransport() override;

    UdpTransport(const UdpTransport&) = delete;
    UdpTransport& operator=(const UdpTransport&) = delete;

    void initialize(const std::string& uri) override;
    void finalize() override;
    bool send(ByteSpan frame) override;
    std::optional<std::vector<std::byte>> receive() override;

    // The actual bound port (useful when the URI asked for port 0).
    std::uint16_t bound_port() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace transport
}  // namespace pyfmi_interop
