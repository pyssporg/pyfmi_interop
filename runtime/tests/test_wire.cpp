#include "pyfmi_interop/runtime/payload.hpp"
#include "pyfmi_interop/runtime/wire.hpp"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

namespace {

using pyfmi_interop::wire::ErrorCode;
using pyfmi_interop::wire::ModelIdSignal;
using pyfmi_interop::wire::PayloadFormat;

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

std::string to_hex(const std::vector<std::uint8_t>& bytes) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string text;
    text.reserve(bytes.size() * 2);
    for (const std::uint8_t byte : bytes) {
        text.push_back(digits[byte >> 4u]);
        text.push_back(digits[byte & 0x0Fu]);
    }
    return text;
}

void write_u16(std::vector<std::uint8_t>& bytes, std::size_t offset, std::uint16_t value) {
    bytes[offset] = static_cast<std::uint8_t>(value & 0xFFu);
    bytes[offset + 1] = static_cast<std::uint8_t>((value >> 8u) & 0xFFu);
}

void write_u32(std::vector<std::uint8_t>& bytes, std::size_t offset, std::uint32_t value) {
    for (int index = 0; index < 4; ++index) {
        bytes[offset + static_cast<std::size_t>(index)] =
            static_cast<std::uint8_t>((value >> (8 * index)) & 0xFFu);
    }
}

// Recompute the header CRC after a deliberate field mutation, so the next
// check reached is the one the test targets.
void refresh_header_crc(std::vector<std::uint8_t>& bytes) {
    const std::uint32_t crc = pyfmi_interop::wire::crc32(bytes.data(), 52);
    write_u32(bytes, 52, crc);
}

ErrorCode decode_error(const std::vector<std::uint8_t>& bytes) {
    return pyfmi_interop::wire::decode_frame(std::string_view(
        reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code;
}

std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize> demo_model_id() {
    return pyfmi_interop::wire::model_id(
        "demo", std::vector<ModelIdSignal>{{1, 1}, {2, 2}});
}

const std::string kModelIdHex = "d6b64a33d05b491b";
const std::string kEmptyFrameHex =
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "00000000000000000000000000000000"
    "ce540190";
const std::string kHelloFrameHex =
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "0500000086a610360000000000000000"
    "630bef06"
    "68656c6c6f";

std::string range_256() {
    std::string text;
    text.reserve(512);
    for (int value = 0; value < 256; ++value) {
        static constexpr char digits[] = "0123456789abcdef";
        text.push_back(digits[value >> 4]);
        text.push_back(digits[value & 0x0F]);
    }
    return text;
}

const std::string kBoundaryFrameHex =
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "00010000738c05290000000000000000"
    "c684aecf" + range_256();

pyfmi_interop::wire::EncodeResult encode_demo(const std::string& payload,
                                              PayloadFormat format = PayloadFormat::Opaque) {
    return pyfmi_interop::wire::encode_frame(demo_model_id(), payload, 7, 42,
                                             1700000000000000000ULL, format);
}

}  // namespace

int main() {
    // CRC-32/ISO-HDLC check value.
    if (pyfmi_interop::wire::crc32(std::string_view("123456789")) != 0xCBF43926u) {
        return fail("crc32 check value");
    }

    // Model-id derivation is v2: the interface only, no timing.
    const auto demo_id = demo_model_id();
    if (to_hex(std::vector<std::uint8_t>(demo_id.begin(), demo_id.end())) != kModelIdHex) {
        return fail("model id demo");
    }
    const auto second = pyfmi_interop::wire::model_id(
        "demo_model",
        std::vector<ModelIdSignal>{{5, 1}, {2, 4}, {1, 1}, {4, 2}, {3, 3}});
    if (to_hex(std::vector<std::uint8_t>(second.begin(), second.end())) !=
        "068406171f053c51") {
        return fail("model id demo_model");
    }

    if (pyfmi_interop::wire::kHeaderSize != 56 ||
        pyfmi_interop::wire::kWireVersion != 2) {
        return fail("v2 constants");
    }

    // Golden v2 frames (payload format protobuf).
    const auto empty = encode_demo("");
    if (!empty || to_hex(empty.frame) != kEmptyFrameHex) {
        return fail("golden empty frame");
    }
    const auto hello = encode_demo("hello");
    if (!hello || to_hex(hello.frame) != kHelloFrameHex) {
        return fail("golden hello frame");
    }
    std::string boundary_payload;
    for (int value = 0; value < 256; ++value) {
        boundary_payload.push_back(static_cast<char>(value));
    }
    const auto boundary = encode_demo(boundary_payload);
    if (!boundary || to_hex(boundary.frame) != kBoundaryFrameHex) {
        return fail("golden 256-byte frame");
    }

    // Round trip.
    const auto decoded = pyfmi_interop::wire::decode_frame(std::string_view(
        reinterpret_cast<const char*>(hello.frame.data()), hello.frame.size()));
    if (!decoded) {
        return fail("decode hello");
    }
    if (decoded.frame.header.model_id != demo_model_id() ||
        decoded.frame.header.wire_version != 2 ||
        decoded.frame.header.header_size != 56 ||
        decoded.frame.header.instance != 7 || decoded.frame.header.sequence != 42 ||
        decoded.frame.header.timestamp_ns != 1700000000000000000ULL ||
        decoded.frame.header.payload_length != 5 ||
        decoded.frame.header.payload_crc32 != 0x3610A686u ||
        decoded.frame.header.payload_format != PayloadFormat::Opaque ||
        decoded.frame.header.flags != 0 || decoded.frame.header.reserved != 0 ||
        decoded.frame.payload != std::vector<std::uint8_t>{'h', 'e', 'l', 'l', 'o'}) {
        return fail("decoded header/payload");
    }

    // Opaque and packed formats are carried and exposed unchanged.
    for (const PayloadFormat format :
         {PayloadFormat::Opaque, PayloadFormat::Protobuf, PayloadFormat::Packed}) {
        const auto encoded = encode_demo("payload", format);
        if (!encoded) {
            return fail("encode explicit payload format");
        }
        const auto result = pyfmi_interop::wire::decode_frame(std::string_view(
            reinterpret_cast<const char*>(encoded.frame.data()), encoded.frame.size()));
        if (!result || result.frame.header.payload_format != format) {
            return fail("decode explicit payload format");
        }
    }

    // Truncation below the fixed header.
    for (const std::size_t length : {std::size_t{0}, std::size_t{1}, std::size_t{55}}) {
        const auto truncated = pyfmi_interop::wire::decode_frame(std::string_view(
            reinterpret_cast<const char*>(hello.frame.data()), length));
        if (truncated.error.code != ErrorCode::TruncatedFrame) {
            return fail("truncated header must be TruncatedFrame");
        }
    }

    // Typed header failures, each with a valid recomputed header CRC so the
    // targeted check is the one that fires.
    {
        auto bytes = hello.frame;
        bytes[0] = 'X';
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::InvalidMagic) {
            return fail("bad magic");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 4, 1);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::UnsupportedWireVersion) {
            return fail("v1 frame must be rejected");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 6, 48);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::InvalidHeaderSize) {
            return fail("bad header size");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 46, 1);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::NonZeroFlags) {
            return fail("nonzero flags");
        }
    }
    {
        auto bytes = hello.frame;
        write_u32(bytes, 48, 1);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::NonZeroReserved) {
            return fail("nonzero reserved");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 44, 3);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::UnsupportedPayloadFormat) {
            return fail("unknown payload format");
        }
    }
    {
        auto bytes = hello.frame;
        bytes[16] ^= 0x01u;  // instance byte, CRC not refreshed
        if (decode_error(bytes) != ErrorCode::HeaderChecksumError) {
            return fail("bad header CRC");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.back() ^= 0x01u;
        if (decode_error(bytes) != ErrorCode::PayloadChecksumError) {
            return fail("bad payload CRC");
        }
    }
    {
        auto bytes = hello.frame;
        write_u32(bytes, 36, 0xFFFFFFFFu);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::LengthOverflow) {
            return fail("declared length beyond uint32");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.pop_back();
        if (decode_error(bytes) != ErrorCode::LengthOverflow) {
            return fail("frame shorter than declared");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.push_back(0x00u);
        if (decode_error(bytes) != ErrorCode::TrailingBytes) {
            return fail("trailing bytes");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 44, 9);
        refresh_header_crc(bytes);
        if (decode_error(bytes) != ErrorCode::UnsupportedPayloadFormat) {
            return fail("encode/decode unknown format");
        }
        const auto encoded = encode_demo("x", static_cast<PayloadFormat>(9));
        if (encoded || encoded.error.code != ErrorCode::FieldRangeError) {
            return fail("encoder must reject an unknown payload format");
        }
    }

    // Exactly one wire mode define, the payload layer reports it, and the
    // default envelope format follows the same selection.
#if defined(PYFMI_INTEROP_WIRE_PROTOBUF) && defined(PYFMI_INTEROP_WIRE_RAW)
    return fail("both wire mode defines are set");
#elif !defined(PYFMI_INTEROP_WIRE_PROTOBUF) && !defined(PYFMI_INTEROP_WIRE_RAW)
    return fail("no wire mode define is set");
#elif defined(PYFMI_INTEROP_WIRE_PROTOBUF)
    if (std::strcmp(pyfmi_interop::wire::payload_mode_name(), "protobuf") != 0 ||
        !pyfmi_interop::wire::protobuf_payloads() ||
        pyfmi_interop::wire::default_payload_format() != PayloadFormat::Protobuf) {
        return fail("protobuf mode reporting");
    }
#else
    if (std::strcmp(pyfmi_interop::wire::payload_mode_name(), "raw") != 0 ||
        pyfmi_interop::wire::protobuf_payloads() ||
        pyfmi_interop::wire::default_payload_format() != PayloadFormat::Opaque) {
        return fail("raw mode reporting");
    }
#endif

    return EXIT_SUCCESS;
}
