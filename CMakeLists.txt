cmake_minimum_required(VERSION 3.21)

project(pyfmi_distributed VERSION 0.1.0 LANGUAGES CXX)

option(PYFMI_DIST_BUILD_TESTS "Build the C++ runtime tests" ON)
option(PYFMI_DIST_ENABLE_HLA "Compile the IEEE 1516 HLA transport stub" OFF)
option(PYFMI_DIST_ENABLE_DIS "Compile the IEEE 1278 DIS transport stub" OFF)
option(PYFMI_DIST_ENABLE_DCP "Compile the ASAM X-DCP transport adapter" OFF)
option(PYFMI_DIST_ENABLE_ROS2 "Compile the ROS 2 transport stub" OFF)
option(PYFMI_DIST_ENABLE_ED247 "Compile the ED-247 transport stub" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Both the static runtime and the FMI shared library land in build/runtime so
# that pyfmi_distributed.native.default_runtime_library_path() finds them.
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/runtime)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/runtime)

include(CTest)

add_subdirectory(runtime)
