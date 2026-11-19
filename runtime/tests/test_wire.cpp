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
using pyfmi_interop::wire::Frame;
using pyfmi_interop::wire::ModelIdSignal;

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
    const std::uint32_t crc = pyfmi_interop::wire::crc32(bytes.data(), 44);
    write_u32(bytes, 44, crc);
}

std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize> demo_model_id() {
    return pyfmi_interop::wire::model_id(
        "demo", 0.01, std::vector<ModelIdSignal>{{1, 1}, {2, 2}});
}

const std::string kModelIdHex = "ee78acea761957f0";
const std::string kEmptyFrameHex =
    "50464d4901003000ee78acea761957f0"
    "070000002a0000000000000000002a36fe9c9717"
    "0000000000000000"
    "1880f4c4";
const std::string kHelloFrameHex =
    "50464d4901003000ee78acea761957f0"
    "070000002a0000000000000000002a36fe9c9717"
    "0500000086a61036"
    "81c1ab1c"
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
    "50464d4901003000ee78acea761957f0"
    "070000002a0000000000000000002a36fe9c9717"
    "00010000738c0529"
    "130ae3cc" + range_256();

pyfmi_interop::wire::EncodeResult encode_demo(const std::string& payload) {
    return pyfmi_interop::wire::encode_frame(demo_model_id(), payload, 7, 42,
                                            1700000000000000000ULL);
}

}  // namespace

int main() {
    // CRC-32/ISO-HDLC check value.
    if (pyfmi_interop::wire::crc32(std::string_view("123456789")) != 0xCBF43926u) {
        return fail("crc32 check value");
    }

    // Model-id parity with Python for two distinct models.
    const auto demo_id = demo_model_id();
    if (to_hex(std::vector<std::uint8_t>(demo_id.begin(), demo_id.end())) != kModelIdHex) {
        return fail("model id demo");
    }
    const auto second = pyfmi_interop::wire::model_id(
        "demo_model", 0.01,
        std::vector<ModelIdSignal>{{5, 1}, {2, 4}, {1, 1}, {4, 2}, {3, 3}});
    if (to_hex(std::vector<std::uint8_t>(second.begin(), second.end())) !=
        "983f897eb99c8464") {
        return fail("model id demo_model");
    }

    // Golden frames from the Python tests.
    const pyfmi_interop::wire::EncodeResult empty = encode_demo("");
    if (!empty || to_hex(empty.frame) != kEmptyFrameHex) {
        return fail("golden empty frame");
    }
    const pyfmi_interop::wire::EncodeResult hello = encode_demo("hello");
    if (!hello || to_hex(hello.frame) != kHelloFrameHex) {
        return fail("golden hello frame");
    }
    std::string boundary_payload;
    for (int value = 0; value < 256; ++value) {
        boundary_payload.push_back(static_cast<char>(value));
    }
    const pyfmi_interop::wire::EncodeResult boundary = encode_demo(boundary_payload);
    if (!boundary || to_hex(boundary.frame) != kBoundaryFrameHex) {
        return fail("golden 256-byte frame");
    }

    // Round trip.
    const pyfmi_interop::wire::DecodeResult decoded = pyfmi_interop::wire::decode_frame(
        std::string_view(reinterpret_cast<const char*>(hello.frame.data()), hello.frame.size()));
    if (!decoded) {
        return fail("decode hello");
    }
    if (decoded.frame.header.model_id != demo_model_id() || decoded.frame.header.instance != 7 ||
        decoded.frame.header.sequence != 42 ||
        decoded.frame.header.timestamp_ns != 1700000000000000000ULL ||
        decoded.frame.header.payload_length != 5 || decoded.frame.header.payload_crc32 != 0x3610A686u ||
        decoded.frame.payload != std::vector<std::uint8_t>{'h', 'e', 'l', 'l', 'o'}) {
        return fail("decoded header/payload");
    }

    // Truncation below the fixed header.
    for (const std::size_t length : {std::size_t{0}, std::size_t{1}, std::size_t{47}}) {
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
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::InvalidMagic) {
            return fail("bad magic");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 4, 2);
        refresh_header_crc(bytes);
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::UnsupportedWireVersion) {
            return fail("bad wire version");
        }
    }
    {
        auto bytes = hello.frame;
        write_u16(bytes, 6, 47);
        refresh_header_crc(bytes);
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::InvalidHeaderSize) {
            return fail("bad header size");
        }
    }
    {
        auto bytes = hello.frame;
        bytes[47] ^= 0x01u;
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::HeaderChecksumError) {
            return fail("bad header CRC");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.back() ^= 0x01u;
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::PayloadChecksumError) {
            return fail("bad payload CRC");
        }
    }
    {
        auto bytes = hello.frame;
        write_u32(bytes, 36, 0xFFFFFFFFu);
        refresh_header_crc(bytes);
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::LengthOverflow) {
            return fail("declared length beyond uint32");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.pop_back();
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::LengthOverflow) {
            return fail("frame shorter than declared");
        }
    }
    {
        auto bytes = hello.frame;
        bytes.push_back(0x00u);
        if (pyfmi_interop::wire::decode_frame(std::string_view(
                reinterpret_cast<const char*>(bytes.data()), bytes.size())).error.code !=
            ErrorCode::TrailingBytes) {
            return fail("trailing bytes");
        }
    }

    // Exactly one wire mode define, and the payload layer reports it.
#if defined(PYFMI_INTEROP_WIRE_PROTOBUF) && defined(PYFMI_INTEROP_WIRE_RAW)
    return fail("both wire mode defines are set");
#elif !defined(PYFMI_INTEROP_WIRE_PROTOBUF) && !defined(PYFMI_INTEROP_WIRE_RAW)
    return fail("no wire mode define is set");
#elif defined(PYFMI_INTEROP_WIRE_PROTOBUF)
    if (std::strcmp(pyfmi_interop::wire::payload_mode_name(), "protobuf") != 0 ||
        !pyfmi_interop::wire::protobuf_payloads()) {
        return fail("protobuf mode reporting");
    }
#else
    if (std::strcmp(pyfmi_interop::wire::payload_mode_name(), "raw") != 0 ||
        pyfmi_interop::wire::protobuf_payloads()) {
        return fail("raw mode reporting");
    }
#endif

    return EXIT_SUCCESS;
}
