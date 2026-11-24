#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

// Byte-frame transport seam.  A transport carries whole wire frames
// (docs/wire.md) without interpreting the payload.  Every call is
// non-blocking: send() returns false when the backend would block, and
// receive() returns the newest queued frame or an empty optional.
namespace pyfmi_interop {

// Non-owning byte view.  The target ABI is `ByteSpan`, but
// this repository builds as C++17, where std::span does not exist; ByteSpan is
// the C++17 equivalent and is implicitly constructible from a vector or array.
class ByteSpan {
public:
    using value_type = std::byte;
    using iterator = const std::byte*;

    constexpr ByteSpan() noexcept = default;
    constexpr ByteSpan(const std::byte* data, std::size_t size) noexcept
        : data_(data), size_(size) {}

    template <std::size_t N>
    constexpr ByteSpan(const std::array<std::byte, N>& bytes) noexcept
        : data_(bytes.data()), size_(N) {}

    ByteSpan(const std::vector<std::byte>& bytes) noexcept
        : data_(bytes.data()), size_(bytes.size()) {}

    constexpr const std::byte* data() const noexcept { return data_; }
    constexpr std::size_t size() const noexcept { return size_; }
    constexpr bool empty() const noexcept { return size_ == 0; }
    constexpr const std::byte* begin() const noexcept { return data_; }
    constexpr const std::byte* end() const noexcept { return data_ + size_; }

private:
    const std::byte* data_ = nullptr;
    std::size_t size_ = 0;
};

struct TransportStats {
    std::uint64_t frames_sent = 0;
    std::uint64_t frames_received = 0;
    std::uint64_t crc_errors = 0;
    std::uint64_t format_errors = 0;
    std::uint64_t model_id_mismatches = 0;
    std::uint64_t dropped_stale = 0;
};

// Transport configuration is rejected by throwing TransportError; the
// realtime step loop never allocates or throws on the success path.
class TransportError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Transport {
public:
    virtual ~Transport() = default;

    // Called once before the first step with the full configuration URI
    // (`loopback`, `udp://host:port?peer=host:port`, `tcp://host:port`,
    // `unix:///path` or `unix://@name`, optionally `?peer=`).
    virtual void initialize(const std::string& uri) { (void)uri; }

    // Called once during shutdown.  Must not throw.
    virtual void finalize() {}

    // Non-blocking.  Returns false when the frame could not be accepted
    // (would block, or no peer yet); the caller may skip the frame.
    virtual bool send(ByteSpan frame) = 0;

    // Non-blocking.  Returns the newest queued frame, discarding older ones
    // and counting them as dropped_stale.
    virtual std::optional<std::vector<std::byte>> receive() = 0;

    virtual TransportStats stats() const { return stats_; }

    // Consumer-side counters for failures detected above the byte layer
    // (the FMI facade validates CRCs, payload format, and model id).
    void record_crc_error() noexcept { ++stats_.crc_errors; }
    void record_format_error() noexcept { ++stats_.format_errors; }
    void record_model_id_mismatch() noexcept { ++stats_.model_id_mismatches; }

protected:
    mutable TransportStats stats_{};
};

using TransportFactory = std::unique_ptr<Transport> (*)();

// Registry.  `register_transport` is called from static initializers emitted
// by REGISTER_TRANSPORT; it returns true so the macro can live in a static.
bool register_transport(const std::string& name, TransportFactory factory);

// `name_or_uri` is either a bare scheme (`loopback`) or a full URI whose
// scheme (`udp`, `tcp`, `unix`) selects the backend.  Unknown names throw
// TransportError listing every registered name.
std::unique_ptr<Transport> make_transport(const std::string& name_or_uri);

// Registered names, sorted for deterministic diagnostics.
std::vector<std::string> transport_names();

}  // namespace pyfmi_interop

#define PYFMI_INTEROP_DETAIL_CONCAT_INNER(a, b) a##b
#define PYFMI_INTEROP_DETAIL_CONCAT(a, b) PYFMI_INTEROP_DETAIL_CONCAT_INNER(a, b)

// Static registration.  `factory` must be convertible to
// `std::unique_ptr<pyfmi_interop::Transport> (*)()`.
#define REGISTER_TRANSPORT(name, factory)                                      \
    [[maybe_unused]] static const bool                                         \
        PYFMI_INTEROP_DETAIL_CONCAT(pyfmi_interop_transport_registration_,     \
                                    __LINE__) =                                \
            ::pyfmi_interop::register_transport((name), (factory))
