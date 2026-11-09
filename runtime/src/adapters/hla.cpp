#include "pyfmi_distributed/runtime/adapters/hla.hpp"

namespace pyfmi_distributed {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_DIST_ENABLE_HLA) && PYFMI_DIST_ENABLE_HLA
    return "HLA SDK binding is not implemented yet; this build configured "
           "PYFMI_DIST_ENABLE_HLA=ON but the runtime still contains only a stub";
#else
    return "HLA transport is not compiled in; rebuild with "
           "-DPYFMI_DIST_ENABLE_HLA=ON to enable the IEEE 1516 RTI binding";
#endif
}

}  // namespace

bool HlaTransport::initialize(const TransportConfig&, std::string& error) {
    error = unavailable_reason();
    return false;
}

void HlaTransport::finalize() noexcept {}

bool HlaTransport::available() const noexcept {
    return false;
}

bool HlaTransport::send(const Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

bool HlaTransport::receive(Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

}  // namespace pyfmi_distributed
