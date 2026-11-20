#include "pyfmi_interop/runtime/loopback_transport.hpp"

#include <cstddef>
#include <utility>
#include <vector>

namespace pyfmi_interop {

void LoopbackTransport::initialize(const std::string& uri) {
    (void)uri;
    newest_.reset();
}

void LoopbackTransport::finalize() {
    newest_.reset();
}

bool LoopbackTransport::send(ByteSpan frame) {
    if (newest_) {
        ++stats_.dropped_stale;
    }
    newest_.emplace(frame.begin(), frame.end());
    ++stats_.frames_sent;
    return true;
}

std::optional<std::vector<std::byte>> LoopbackTransport::receive() {
    if (!newest_) {
        return std::nullopt;
    }
    std::vector<std::byte> frame = std::move(*newest_);
    newest_.reset();
    ++stats_.frames_received;
    return frame;
}

namespace {
const bool kLoopbackRegistered = register_transport(
    "loopback", []() -> std::unique_ptr<Transport> {
        return std::make_unique<LoopbackTransport>();
    });
}

}  // namespace pyfmi_interop
