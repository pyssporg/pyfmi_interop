#include "pyfmi_interop/runtime/adapters/dis.hpp"

namespace pyfmi_interop {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_INTEROP_ENABLE_DIS) && PYFMI_INTEROP_ENABLE_DIS
    return "DIS SDK binding is not implemented yet; this build configured "
           "PYFMI_INTEROP_ENABLE_DIS=ON but the runtime still contains only a stub";
#else
    return "DIS transport is not compiled in; rebuild with "
           "-DPYFMI_INTEROP_ENABLE_DIS=ON to enable the IEEE 1278 UDP binding";
#endif
}

}  // namespace

bool DisTransport::initialize(const TransportConfig&, std::string& error) {
    error = unavailable_reason();
    return false;
}

void DisTransport::finalize() noexcept {}

bool DisTransport::available() const noexcept {
    return false;
}

bool DisTransport::send(const Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

bool DisTransport::receive(Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

}  // namespace pyfmi_interop
