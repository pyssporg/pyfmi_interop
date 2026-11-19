#include "pyfmi_interop/runtime/adapters/ros2.hpp"

namespace pyfmi_interop {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_INTEROP_ENABLE_ROS2) && PYFMI_INTEROP_ENABLE_ROS2
    return "ROS 2 SDK binding is not implemented yet; this build configured "
           "PYFMI_INTEROP_ENABLE_ROS2=ON but the runtime still contains only a stub";
#else
    return "ROS 2 transport is not compiled in; rebuild with "
           "-DPYFMI_INTEROP_ENABLE_ROS2=ON to enable the rclcpp binding";
#endif
}

}  // namespace

bool Ros2Transport::initialize(const TransportConfig&, std::string& error) {
    error = unavailable_reason();
    return false;
}

void Ros2Transport::finalize() noexcept {}

bool Ros2Transport::available() const noexcept {
    return false;
}

bool Ros2Transport::send(const Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

bool Ros2Transport::receive(Sample&, std::string& error) {
    error = unavailable_reason();
    return false;
}

}  // namespace pyfmi_interop
