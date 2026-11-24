#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {
namespace transport {

// AF_UNIX SOCK_DGRAM backend.  One datagram is one wire frame, exactly like
// UDP: there is no stream framing.  Addresses are either an absolute pathname
// (`unix:///abs/path.sock`) or an abstract name (`unix://@name`).  Frames
// larger than 65507 bytes are rejected with TransportError; receive drains the
// socket and keeps the newest datagram.
class UnixTransport final : public Transport {
public:
    UnixTransport();
    ~UnixTransport() override;

    UnixTransport(const UnixTransport&) = delete;
    UnixTransport& operator=(const UnixTransport&) = delete;

    void initialize(const std::string& uri) override;
    void finalize() override;
    bool send(ByteSpan frame) override;
    std::optional<std::vector<std::byte>> receive() override;

    // The configured bind address, as written in the URI (`/path` or `@name`).
    std::string bound_path() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace transport
}  // namespace pyfmi_interop
