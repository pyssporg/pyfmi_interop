#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {
namespace transport {

// Stream transport.  It accepts one peer (or connects when the URI carries
// `?peer=`), reassembles the self-delimiting envelope from partial reads, and
// never blocks the step.
class TcpTransport final : public Transport {
public:
    TcpTransport();
    ~TcpTransport() override;

    TcpTransport(const TcpTransport&) = delete;
    TcpTransport& operator=(const TcpTransport&) = delete;

    void initialize(const std::string& uri) override;
    void finalize() override;
    bool send(ByteSpan frame) override;
    std::optional<std::vector<std::byte>> receive() override;

    // The actual bound port (useful when the URI asked for port 0).
    std::uint16_t bound_port() const noexcept;

    // Opaque socket state; public only so the small POSIX helpers can name it.
    struct Impl;

private:
    std::unique_ptr<Impl> impl_;
};

}  // namespace transport
}  // namespace pyfmi_interop
