#pragma once

#include <cstddef>
#include <string>

#include "pyfmi_distributed/runtime/transport.hpp"

namespace pyfmi_distributed {

// In-process transport used by tests and by generated models that run without
// a network.  send() copies the frame into preallocated storage; receive()
// returns the most recently sent frame.
//
// Storage is grown in initialize() when the "signal_count" option is present
// and, defensively, on the first send/receive whose frame is larger than the
// buffer.  After that the numeric fast path does not allocate.  Copying a
// String Value can allocate unless the destination string already has enough
// capacity; this is the documented string exception.
class LoopbackTransport final : public Transport {
public:
    LoopbackTransport() = default;

    bool initialize(const TransportConfig& config, std::string& error) override;
    void finalize() noexcept override;
    bool available() const noexcept override;
    bool send(const Sample& sample, std::string& error) override;
    bool receive(Sample& sample, std::string& error) override;

private:
    Sample buffer_;
    bool has_sample_ = false;
};

}  // namespace pyfmi_distributed
