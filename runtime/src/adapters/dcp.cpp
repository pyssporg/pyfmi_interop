#include "pyfmi_interop/runtime/adapters/dcp.hpp"

namespace pyfmi_interop {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_INTEROP_ENABLE_DCP) && PYFMI_INTEROP_ENABLE_DCP
    return "ASAM X-DCP adapter is built against DCPLib but the signal mapping "
           "is not implemented yet";
#else
    return "ASAM X-DCP adapter is not compiled in; configure with "
           "-DPYFMI_INTEROP_ENABLE_DCP=ON to link DCPLib";
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

}  // namespace pyfmi_interop
