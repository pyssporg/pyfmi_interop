#include "pyfmi_interop/runtime/wire.hpp"

#include <algorithm>
#include <cstring>
#include <limits>

namespace pyfmi_interop {
namespace wire {
namespace {

constexpr std::uint32_t kCrc32Polynomial = 0xEDB88320u;
constexpr std::uint32_t kCrc32Init = 0xFFFFFFFFu;
constexpr std::uint32_t kCrc32XorOut = 0xFFFFFFFFu;

// Offset of the header CRC field: the CRC covers bytes [0, 44).
constexpr std::size_t kHeaderCrcOffset = 44;

std::uint32_t crc32_table_entry(std::uint32_t index) noexcept {
    std::uint32_t value = index;
    for (int bit = 0; bit < 8; ++bit) {
        value = (value & 1u) != 0u ? (value >> 1u) ^ kCrc32Polynomial : value >> 1u;
    }
    return value;
}

const std::array<std::uint32_t, 256>& crc32_table() {
    static const std::array<std::uint32_t, 256> table = [] {
        std::array<std::uint32_t, 256> values{};
        for (std::uint32_t index = 0; index < 256u; ++index) {
            values[index] = crc32_table_entry(index);
        }
        return values;
    }();
    return table;
}

void write_u16(std::uint8_t* target, std::uint16_t value) noexcept {
    target[0] = static_cast<std::uint8_t>(value & 0xFFu);
    target[1] = static_cast<std::uint8_t>((value >> 8u) & 0xFFu);
}

void write_u32(std::uint8_t* target, std::uint32_t value) noexcept {
    target[0] = static_cast<std::uint8_t>(value & 0xFFu);
    target[1] = static_cast<std::uint8_t>((value >> 8u) & 0xFFu);
    target[2] = static_cast<std::uint8_t>((value >> 16u) & 0xFFu);
    target[3] = static_cast<std::uint8_t>((value >> 24u) & 0xFFu);
}

void write_u64(std::uint8_t* target, std::uint64_t value) noexcept {
    for (int index = 0; index < 8; ++index) {
        target[index] = static_cast<std::uint8_t>((value >> (8 * index)) & 0xFFu);
    }
}

std::uint16_t read_u16(const std::uint8_t* source) noexcept {
    return static_cast<std::uint16_t>(source[0]) |
           static_cast<std::uint16_t>(static_cast<std::uint16_t>(source[1]) << 8u);
}

std::uint32_t read_u32(const std::uint8_t* source) noexcept {
    return static_cast<std::uint32_t>(source[0]) |
           (static_cast<std::uint32_t>(source[1]) << 8u) |
           (static_cast<std::uint32_t>(source[2]) << 16u) |
           (static_cast<std::uint32_t>(source[3]) << 24u);
}

std::uint64_t read_u64(const std::uint8_t* source) noexcept {
    std::uint64_t value = 0;
    for (int index = 7; index >= 0; --index) {
        value = (value << 8u) | source[index];
    }
    return value;
}

inline std::uint32_t rotate_right(std::uint32_t value, int bits) noexcept {
    return (value >> bits) | (value << (32 - bits));
}

void sha256_compress(std::uint32_t state[8], const std::uint8_t block[64]) noexcept {
    static constexpr std::uint32_t constants[64] = {
        0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
        0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
        0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
        0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
        0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
        0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
        0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
        0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
        0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
        0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
        0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
    };

    std::uint32_t words[64];
    for (int index = 0; index < 16; ++index) {
        const std::uint8_t* chunk = block + index * 4;
        words[index] = (static_cast<std::uint32_t>(chunk[0]) << 24u) |
                       (static_cast<std::uint32_t>(chunk[1]) << 16u) |
                       (static_cast<std::uint32_t>(chunk[2]) << 8u) |
                       static_cast<std::uint32_t>(chunk[3]);
    }
    for (int index = 16; index < 64; ++index) {
        const std::uint32_t s0 = rotate_right(words[index - 15], 7) ^
                                 rotate_right(words[index - 15], 18) ^
                                 (words[index - 15] >> 3u);
        const std::uint32_t s1 = rotate_right(words[index - 2], 17) ^
                                 rotate_right(words[index - 2], 19) ^
                                 (words[index - 2] >> 10u);
        words[index] = words[index - 16] + s0 + words[index - 7] + s1;
    }

    std::uint32_t a = state[0];
    std::uint32_t b = state[1];
    std::uint32_t c = state[2];
    std::uint32_t d = state[3];
    std::uint32_t e = state[4];
    std::uint32_t f = state[5];
    std::uint32_t g = state[6];
    std::uint32_t h = state[7];

    for (int index = 0; index < 64; ++index) {
        const std::uint32_t s1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
        const std::uint32_t choice = (e & f) ^ (~e & g);
        const std::uint32_t temp1 = h + s1 + choice + constants[index] + words[index];
        const std::uint32_t s0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
        const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        const std::uint32_t temp2 = s0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

using Sha256Digest = std::array<std::uint8_t, 32>;

Sha256Digest sha256_bytes(const std::vector<std::uint8_t>& input) noexcept {
    std::uint32_t state[8] = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
    };

    const std::size_t full_blocks = input.size() / 64u;
    for (std::size_t block = 0; block < full_blocks; ++block) {
        sha256_compress(state, input.data() + block * 64u);
    }

    std::vector<std::uint8_t> tail(input.begin() + static_cast<std::ptrdiff_t>(full_blocks * 64u),
                                   input.end());
    const std::uint64_t bit_length = static_cast<std::uint64_t>(input.size()) * 8u;
    tail.push_back(0x80u);
    while ((tail.size() % 64u) != 56u) {
        tail.push_back(0x00u);
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
        tail.push_back(static_cast<std::uint8_t>((bit_length >> shift) & 0xFFu));
    }
    for (std::size_t offset = 0; offset < tail.size(); offset += 64u) {
        sha256_compress(state, tail.data() + offset);
    }

    Sha256Digest digest{};
    for (int index = 0; index < 8; ++index) {
        digest[static_cast<std::size_t>(index) * 4u] =
            static_cast<std::uint8_t>((state[index] >> 24u) & 0xFFu);
        digest[static_cast<std::size_t>(index) * 4u + 1u] =
            static_cast<std::uint8_t>((state[index] >> 16u) & 0xFFu);
        digest[static_cast<std::size_t>(index) * 4u + 2u] =
            static_cast<std::uint8_t>((state[index] >> 8u) & 0xFFu);
        digest[static_cast<std::size_t>(index) * 4u + 3u] =
            static_cast<std::uint8_t>(state[index] & 0xFFu);
    }
    return digest;
}

void append_u64_le(std::vector<std::uint8_t>& target, std::uint64_t value) {
    for (int index = 0; index < 8; ++index) {
        target.push_back(static_cast<std::uint8_t>((value >> (8 * index)) & 0xFFu));
    }
}

}  // namespace

const char* error_code_name(ErrorCode code) noexcept {
    switch (code) {
        case ErrorCode::None:
            return "None";
        case ErrorCode::InvalidMagic:
            return "InvalidMagic";
        case ErrorCode::UnsupportedWireVersion:
            return "UnsupportedWireVersion";
        case ErrorCode::InvalidHeaderSize:
            return "InvalidHeaderSize";
        case ErrorCode::TruncatedFrame:
            return "TruncatedFrame";
        case ErrorCode::LengthOverflow:
            return "LengthOverflow";
        case ErrorCode::TrailingBytes:
            return "TrailingBytes";
        case ErrorCode::ChecksumError:
            return "ChecksumError";
        case ErrorCode::HeaderChecksumError:
            return "HeaderChecksumError";
        case ErrorCode::PayloadChecksumError:
            return "PayloadChecksumError";
        case ErrorCode::FieldRangeError:
            return "FieldRangeError";
    }
    return "WireError";
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) noexcept {
    const std::array<std::uint32_t, 256>& table = crc32_table();
    std::uint32_t crc = kCrc32Init;
    for (std::size_t index = 0; index < size; ++index) {
        crc = table[(crc ^ data[index]) & 0xFFu] ^ (crc >> 8u);
    }
    return crc ^ kCrc32XorOut;
}

std::uint32_t crc32(std::string_view data) noexcept {
    return crc32(reinterpret_cast<const std::uint8_t*>(data.data()), data.size());
}

std::array<std::uint8_t, 32> sha256(const std::uint8_t* data, std::size_t size) noexcept {
    const std::vector<std::uint8_t> input(data, data + size);
    return sha256_bytes(input);
}

std::array<std::uint8_t, kModelIdSize> model_id(
    std::string_view name, double step_size_s,
    const std::vector<ModelIdSignal>& signals) {
    std::vector<std::uint8_t> input;
    static constexpr char domain[] = "pyfmi_interop.model-id.v1";
    input.insert(input.end(), domain, domain + sizeof(domain));  // includes the NUL
    input.insert(input.end(), name.begin(), name.end());
    input.push_back(0x00u);

    std::uint64_t step_bits = 0;
    static_assert(sizeof(step_bits) == sizeof(step_size_s), "double must be 64-bit");
    std::memcpy(&step_bits, &step_size_s, sizeof(step_bits));
    append_u64_le(input, step_bits);

    std::vector<ModelIdSignal> ordered = signals;
    std::sort(ordered.begin(), ordered.end(),
              [](const ModelIdSignal& left, const ModelIdSignal& right) {
                  return left.value_reference < right.value_reference;
              });
    for (const ModelIdSignal& signal : ordered) {
        input.push_back(static_cast<std::uint8_t>(signal.value_reference & 0xFFu));
        input.push_back(static_cast<std::uint8_t>((signal.value_reference >> 8u) & 0xFFu));
        input.push_back(static_cast<std::uint8_t>((signal.value_reference >> 16u) & 0xFFu));
        input.push_back(static_cast<std::uint8_t>((signal.value_reference >> 24u) & 0xFFu));
        input.push_back(signal.data_type);
    }

    const Sha256Digest digest = sha256_bytes(input);
    std::array<std::uint8_t, kModelIdSize> result{};
    std::copy(digest.begin(), digest.begin() + static_cast<std::ptrdiff_t>(kModelIdSize),
              result.begin());
    return result;
}

EncodeResult encode_frame(const std::array<std::uint8_t, kModelIdSize>& model_id,
                          std::string_view payload, std::uint32_t instance,
                          std::uint64_t sequence, std::uint64_t timestamp_ns) {
    EncodeResult result;
    if (payload.size() > std::numeric_limits<std::uint32_t>::max()) {
        result.error = {ErrorCode::LengthOverflow, "payload exceeds uint32 length"};
        return result;
    }
    const std::uint64_t total = static_cast<std::uint64_t>(kHeaderSize) + payload.size();
    if (total > std::numeric_limits<std::uint32_t>::max()) {
        result.error = {ErrorCode::LengthOverflow,
                        "payload length plus header size exceeds uint32"};
        return result;
    }

    const std::uint32_t payload_crc32 = crc32(payload);
    std::vector<std::uint8_t>& frame = result.frame;
    frame.resize(kHeaderSize + payload.size());
    std::uint8_t* prefix = frame.data();
    write_u32(prefix, 0x494D4650u);  // "PFMI" little-endian
    write_u16(prefix + 4, kWireVersion);
    write_u16(prefix + 6, static_cast<std::uint16_t>(kHeaderSize));
    std::copy(model_id.begin(), model_id.end(), prefix + 8);
    write_u32(prefix + 16, instance);
    write_u64(prefix + 20, sequence);
    write_u64(prefix + 28, timestamp_ns);
    write_u32(prefix + 36, static_cast<std::uint32_t>(payload.size()));
    write_u32(prefix + 40, payload_crc32);

    const std::uint32_t header_crc32 = crc32(prefix, kHeaderCrcOffset);
    write_u32(prefix + kHeaderCrcOffset, header_crc32);
    if (!payload.empty()) {
        std::memcpy(prefix + kHeaderSize, payload.data(), payload.size());
    }

    result.error = {};
    return result;
}

DecodeResult decode_frame(std::string_view buffer) {
    DecodeResult result;
    const auto* data = reinterpret_cast<const std::uint8_t*>(buffer.data());
    if (buffer.size() < kHeaderSize) {
        result.error = {ErrorCode::TruncatedFrame,
                        "buffer holds " + std::to_string(buffer.size()) +
                            " bytes, shorter than the 48-byte header"};
        return result;
    }

    Header& header = result.frame.header;
    std::copy(data, data + 4, header.magic.begin());
    header.wire_version = read_u16(data + 4);
    header.header_size = read_u16(data + 6);
    std::copy(data + 8, data + 16, header.model_id.begin());
    header.instance = read_u32(data + 16);
    header.sequence = read_u64(data + 20);
    header.timestamp_ns = read_u64(data + 28);
    header.payload_length = read_u32(data + 36);
    header.payload_crc32 = read_u32(data + 40);
    header.header_crc32 = read_u32(data + 44);

    static constexpr std::array<std::uint8_t, 4> magic{{'P', 'F', 'M', 'I'}};
    if (header.magic != magic) {
        result.error = {ErrorCode::InvalidMagic, "bad magic"};
        return result;
    }
    if (header.wire_version != kWireVersion) {
        result.error = {ErrorCode::UnsupportedWireVersion,
                        "wire version " + std::to_string(header.wire_version) +
                            " is not supported (expected 1)"};
        return result;
    }
    if (header.header_size != kHeaderSize) {
        result.error = {ErrorCode::InvalidHeaderSize,
                        "header size " + std::to_string(header.header_size) +
                            " does not match 48"};
        return result;
    }

    const std::uint32_t actual_header_crc32 = crc32(data, kHeaderCrcOffset);
    if (actual_header_crc32 != header.header_crc32) {
        result.error = {ErrorCode::HeaderChecksumError, "header CRC32 mismatch"};
        return result;
    }

    const std::uint64_t max_payload =
        std::numeric_limits<std::uint32_t>::max() - static_cast<std::uint64_t>(kHeaderSize);
    if (header.payload_length > max_payload) {
        result.error = {ErrorCode::LengthOverflow,
                        "payload length overflows the uint32 frame length"};
        return result;
    }
    const std::size_t total = kHeaderSize + header.payload_length;
    if (total > buffer.size()) {
        result.error = {ErrorCode::LengthOverflow,
                        "frame declares more bytes than the buffer holds"};
        return result;
    }
    if (total < buffer.size()) {
        result.error = {ErrorCode::TrailingBytes,
                        "frame is shorter than the buffer"};
        return result;
    }

    result.frame.payload.assign(data + kHeaderSize, data + total);
    const std::uint32_t actual_payload_crc32 = crc32(result.frame.payload.data(),
                                                     result.frame.payload.size());
    if (actual_payload_crc32 != header.payload_crc32) {
        result.error = {ErrorCode::PayloadChecksumError, "payload CRC32 mismatch"};
        return result;
    }

    result.error = {};
    return result;
}

}  // namespace wire
}  // namespace pyfmi_interop
