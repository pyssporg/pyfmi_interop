#pragma once

#include <optional>
#include <vector>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {

// In-process reference transport used by tests and single-process models.
// send() stores the newest frame and drops an older unread one; receive()
// returns it and clears the slot.
class LoopbackTransport final : public Transport {
public:
    LoopbackTransport() = default;

    void initialize(const std::string& uri) override;
    void finalize() override;
    bool send(ByteSpan frame) override;
    std::optional<std::vector<std::byte>> receive() override;

private:
    std::optional<std::vector<std::byte>> newest_;
};

}  // namespace pyfmi_interop
