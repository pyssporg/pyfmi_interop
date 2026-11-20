cmake_minimum_required(VERSION 3.21)

project(pyfmi_interop VERSION 0.5.0 LANGUAGES CXX)

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

# A static transport backend registers itself from a static initializer, so the
# archive must be linked with whole-archive wherever it is consumed.
function(pyfmi_interop_link_transport_whole_archive target)
    target_include_directories(${target} PRIVATE
        ${PROJECT_SOURCE_DIR}/src/transport/include)
    if(MSVC)
        target_link_options(${target} PRIVATE
            "/WHOLEARCHIVE:$<TARGET_FILE:pyfmi_interop_transport>")
    elseif(APPLE)
        target_link_libraries(${target} PRIVATE
            "-Wl,-force_load,$<TARGET_FILE:pyfmi_interop_transport>")
    else()
        target_link_libraries(${target} PRIVATE
            "-Wl,--whole-archive"
            "$<TARGET_FILE:pyfmi_interop_transport>"
            "-Wl,--no-whole-archive")
    endif()
endfunction()

add_subdirectory(src/runtime)
add_subdirectory(src/transport)
