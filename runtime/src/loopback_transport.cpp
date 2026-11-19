#include "pyfmi_interop/runtime/loopback_transport.hpp"

#include <cstddef>
#include <string>

namespace pyfmi_interop {
namespace {

void ensure_frame_size(Sample& sample, std::size_t signal_count) {
    if (sample.values.size() < signal_count) {
        sample.values.resize(signal_count);
    }
    if (sample.valid.size() < signal_count) {
        sample.valid.resize(signal_count, static_cast<unsigned char>(0));
    }
}

unsigned char valid_at(const Sample& sample, std::size_t index) {
    return index < sample.valid.size() ? sample.valid[index] : static_cast<unsigned char>(0);
}

void copy_into(const Sample& source, Sample& target) {
    const std::size_t count = source.values.size();
    ensure_frame_size(target, count);
    target.simulation_time = source.simulation_time;
    for (std::size_t index = 0; index < count; ++index) {
        target.values[index].type = source.values[index].type;
        target.values[index].assign_from(source.values[index]);
        target.valid[index] = valid_at(source, index);
    }
}

}  // namespace

bool LoopbackTransport::initialize(const TransportConfig& config, std::string& error) {
    has_sample_ = false;

    if (const std::string* signal_count = config.find("signal_count")) {
        if (!signal_count->empty()) {
            try {
                const unsigned long long parsed = std::stoull(*signal_count);
                buffer_.resize(static_cast<std::size_t>(parsed));
            } catch (...) {
                error = "loopback option 'signal_count' must be a non-negative integer";
                return false;
            }
        }
    }

    return true;
}

void LoopbackTransport::finalize() noexcept {
    has_sample_ = false;
}

bool LoopbackTransport::available() const noexcept {
    return true;
}

bool LoopbackTransport::send(const Sample& sample, std::string& error) {
    if (sample.values.size() != sample.valid.size()) {
        error = "loopback send requires values and valid vectors of equal length";
        return false;
    }

    copy_into(sample, buffer_);
    has_sample_ = true;
    return true;
}

bool LoopbackTransport::receive(Sample& sample, std::string& error) {
    if (!has_sample_) {
        error = "loopback transport has no sample to receive";
        return false;
    }

    copy_into(buffer_, sample);
    return true;
}

}  // namespace pyfmi_interop
