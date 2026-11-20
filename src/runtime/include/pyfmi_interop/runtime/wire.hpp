#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

// C++ end of the versioned wire envelope documented in docs/wire.md.  The
// layout, CRCs, model-id derivation, and error taxonomy mirror the Python
// implementation in pyfmi_interop.wire byte for byte.
namespace pyfmi_interop {
namespace wire {

// Wire v2: 56-byte header, two extra uint16 fields (payload format and flags)
// and a uint32 reserved field before the header CRC.
constexpr std::size_t kHeaderSize = 56;
constexpr std::uint16_t kWireVersion = 2;
constexpr std::size_t kModelIdSize = 8;
// The header CRC covers bytes [0, 52); it is never part of its own input.
constexpr std::size_t kHeaderCrcOffset = 52;

// How the bytes after the header are to be interpreted.  The envelope itself
// never parses them; the receiver compares this tag with its own serializer
// before handing the payload to a codec.
enum class PayloadFormat : std::uint16_t {
    Opaque = 0,
    Protobuf = 1,
    Packed = 2,
};

// Typed failure taxonomy; names match the Python WireError subclasses.
enum class ErrorCode {
    None,
    InvalidMagic,
    UnsupportedWireVersion,
    InvalidHeaderSize,
    NonZeroFlags,
    NonZeroReserved,
    UnsupportedPayloadFormat,
    TruncatedFrame,
    LengthOverflow,
    TrailingBytes,
    ChecksumError,
    HeaderChecksumError,
    PayloadChecksumError,
    FieldRangeError,
};

struct WireError {
    ErrorCode code = ErrorCode::None;
    std::string message;

    explicit operator bool() const noexcept { return code != ErrorCode::None; }
};

const char* error_code_name(ErrorCode code) noexcept;
const char* payload_format_name(PayloadFormat format) noexcept;

// The format this build's payload layer emits: protobuf when the runtime is
// compiled with PYFMI_INTEROP_WIRE_PROTOBUF, opaque otherwise.
PayloadFormat default_payload_format() noexcept;

struct Header {
    std::array<std::uint8_t, 4> magic{{'P', 'F', 'M', 'I'}};
    std::uint16_t wire_version = kWireVersion;
    std::uint16_t header_size = static_cast<std::uint16_t>(kHeaderSize);
    std::array<std::uint8_t, kModelIdSize> model_id{};
    std::uint32_t instance = 0;
    std::uint64_t sequence = 0;
    std::uint64_t timestamp_ns = 0;
    std::uint32_t payload_length = 0;
    std::uint32_t payload_crc32 = 0;
    PayloadFormat payload_format = PayloadFormat::Opaque;
    std::uint16_t flags = 0;
    std::uint32_t reserved = 0;
    std::uint32_t header_crc32 = 0;
};

struct Frame {
    Header header;
    std::vector<std::uint8_t> payload;
};

struct EncodeResult {
    std::vector<std::uint8_t> frame;
    WireError error;

    explicit operator bool() const noexcept { return !error; }
};

struct DecodeResult {
    Frame frame;
    WireError error;

    explicit operator bool() const noexcept { return !error; }
};

// One record of the model-id digest input: `value_reference` as uint32
// little-endian followed by `data_type` as uint8.
struct ModelIdSignal {
    std::uint32_t value_reference = 0;
    std::uint8_t data_type = 0;
};

// Derived interface identity: first 8 bytes of SHA-256 over the domain
// separator, model name + NUL, then one record per signal ordered by value
// reference.  Timing is not part of the identity.
std::array<std::uint8_t, kModelIdSize> model_id(
    std::string_view name,
    const std::vector<ModelIdSignal>& signals);

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) noexcept;
std::uint32_t crc32(std::string_view data) noexcept;
std::array<std::uint8_t, 32> sha256(const std::uint8_t* data, std::size_t size) noexcept;

// `format` defaults to opaque, matching the Python encoder.  A generated
// codec passes its own format explicitly.
EncodeResult encode_frame(const std::array<std::uint8_t, kModelIdSize>& model_id,
                          std::string_view payload, std::uint32_t instance,
                          std::uint64_t sequence, std::uint64_t timestamp_ns,
                          PayloadFormat format = PayloadFormat::Opaque);

DecodeResult decode_frame(std::string_view buffer);

}  // namespace wire
}  // namespace pyfmi_interop
