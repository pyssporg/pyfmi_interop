#include "pyfmi_distributed/runtime/adapters/ed247.hpp"

namespace pyfmi_distributed {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_DIST_ENABLE_ED247) && PYFMI_DIST_ENABLE_ED247
    return "ED-247 SDK binding is not implemented yet; this build configured "
           "PYFMI_DIST_ENABLE_ED247=ON but the runtime still contains only a stub";
#else
    return "ED-247 transport is not compiled in; rebuild with "
           "-DPYFMI_DIST_ENABLE_ED247=ON to enable the ARINC 664 binding";
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

}  // namespace pyfmi_distributed
