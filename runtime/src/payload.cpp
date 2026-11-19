#include "pyfmi_interop/runtime/payload.hpp"

namespace pyfmi_interop {
namespace wire {

const char* payload_mode_name() noexcept {
#if defined(PYFMI_INTEROP_WIRE_PROTOBUF)
    return "protobuf";
#else
    return "raw";
#endif
}

}  // namespace wire
}  // namespace pyfmi_interop
