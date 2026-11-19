#include "pyfmi_interop/runtime/adapters/ed247.hpp"

namespace pyfmi_interop {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_INTEROP_ENABLE_ED247) && PYFMI_INTEROP_ENABLE_ED247
    return "ED-247 SDK binding is not implemented yet; this build configured "
           "PYFMI_INTEROP_ENABLE_ED247=ON but the runtime still contains only a stub";
#else
    return "ED-247 transport is not compiled in; rebuild with "
           "-DPYFMI_INTEROP_ENABLE_ED247=ON to enable the ARINC 664 binding";
#endif
}

}  // namespace

bool Ed247Transport::initialize(const TransportConfig&, std::string& error) {
    error = unavailable_reason();
    return false;
}

void Ed247Transport::finalize() noexcept {}

bool Ed247Transport::available() const noexcept {
    return false;
}

bool Ed247Transport::send(const Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

bool Ed247Transport::receive(Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

}  // namespace pyfmi_interop
