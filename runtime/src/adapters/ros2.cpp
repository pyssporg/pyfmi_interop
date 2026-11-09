#include "pyfmi_distributed/runtime/adapters/ros2.hpp"

namespace pyfmi_distributed {
namespace {

const char* unavailable_reason() {
#if defined(PYFMI_DIST_ENABLE_ROS2) && PYFMI_DIST_ENABLE_ROS2
    return "ROS 2 SDK binding is not implemented yet; this build configured "
           "PYFMI_DIST_ENABLE_ROS2=ON but the runtime still contains only a stub";
#else
    return "ROS 2 transport is not compiled in; rebuild with "
           "-DPYFMI_DIST_ENABLE_ROS2=ON to enable the rclcpp binding";
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

}  // namespace pyfmi_distributed
