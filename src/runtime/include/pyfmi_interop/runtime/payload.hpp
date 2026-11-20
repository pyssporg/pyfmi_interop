#pragma once

#include <string>
#include <string_view>

// Payload layer above the envelope.  The envelope itself is payload-agnostic.
// In `protobuf` builds the generated model implements PayloadCodec against its
// own `<Model>Payload` message; it never hand-rolls protobuf bytes.  In `raw`
// builds the envelope carries caller-supplied bytes unchanged, which is the
// existing opaque-payload behaviour.
namespace pyfmi_interop {
namespace wire {

class PayloadCodec {
public:
    virtual ~PayloadCodec() = default;

    // Serialize the model's current signal values into `payload`.
    virtual bool encode_payload(std::string& payload, std::string& error) const = 0;

    // Apply a serialized payload to the model's signal values.
    virtual bool decode_payload(std::string_view payload, std::string& error) = 0;
};

// Compile-time wire mode exposed to dependents and the tests.
constexpr bool protobuf_payloads() noexcept {
#if defined(PYFMI_INTEROP_WIRE_PROTOBUF)
    return true;
#else
    return false;
#endif
}

const char* payload_mode_name() noexcept;

}  // namespace wire
}  // namespace pyfmi_interop
