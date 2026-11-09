#include "pyfmi_distributed/runtime/adapters/dcp.hpp"

namespace pyfmi_distributed {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_DIST_ENABLE_DCP) && PYFMI_DIST_ENABLE_DCP
    return "ASAM X-DCP adapter is built against DCPLib but the signal mapping "
           "is not implemented yet";
#else
    return "ASAM X-DCP adapter is not compiled in; configure with "
           "-DPYFMI_DIST_ENABLE_DCP=ON to link DCPLib";
#endif
}

}  // namespace

bool DcpTransport::initialize(const TransportConfig&, std::string& error) {
    error = unavailable_reason();
    return false;
}

void DcpTransport::finalize() noexcept {}

bool DcpTransport::available() const noexcept {
    return false;
}

bool DcpTransport::send(const Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

bool DcpTransport::receive(Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

}  // namespace pyfmi_distributed
