cmake_minimum_required(VERSION 3.21)

project(pyfmi_interop VERSION 0.3.0 LANGUAGES CXX)

option(PYFMI_INTEROP_BUILD_TESTS "Build the C++ runtime tests" ON)

# Wire payload mode: protobuf (default when libprotobuf is found) or raw.
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)
include(wire)
pyfmi_interop_resolve_wire()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Both the static runtime and the FMI shared library land in build/runtime so
# that pyfmi_interop.native.default_runtime_library_path() finds them.
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/runtime)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/runtime)

include(CTest)

add_subdirectory(runtime)
