"""CMake project text for a generated model.

The generated project is deliberately thin: it compiles the two generated
translation units, links the reusable static runtime, and exposes the runtime
locations as cache variables.  The wire mode is resolved through the shared
``cmake/wire.cmake`` module, and there is no protocol adapter layer.
"""

from __future__ import annotations

from ..ir import ModelDefinition
from ..schema import proto_filename

__all__ = ["render_cmake"]


def render_cmake(model: ModelDefinition) -> str:
    """Return a deterministic ``CMakeLists.txt`` for ``model``."""

    proto_name = proto_filename(model)

    return f"""cmake_minimum_required(VERSION 3.16)
project({model.name} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(
    PYFMI_INTEROP_RUNTIME_INCLUDE_DIR
    ""
    CACHE PATH
    "Directory containing pyfmi_interop/runtime/*.hpp"
)
set(
    PYFMI_INTEROP_RUNTIME_LIBRARY
    ""
    CACHE FILEPATH
    "Path to the static pyfmi-interop runtime library"
)
set(
    PYFMI_INTEROP_CMAKE_DIR
    ""
    CACHE PATH
    "Directory containing the shared wire.cmake module"
)

if(NOT PYFMI_INTEROP_CMAKE_DIR)
    message(FATAL_ERROR "PYFMI_INTEROP_CMAKE_DIR is required")
endif()
include("${{PYFMI_INTEROP_CMAKE_DIR}}/wire.cmake")
pyfmi_interop_resolve_wire()

if(NOT PYFMI_INTEROP_RUNTIME_INCLUDE_DIR)
    message(FATAL_ERROR "PYFMI_INTEROP_RUNTIME_INCLUDE_DIR is required")
endif()
if(NOT PYFMI_INTEROP_RUNTIME_LIBRARY)
    message(FATAL_ERROR "PYFMI_INTEROP_RUNTIME_LIBRARY is required")
endif()
if(NOT EXISTS "${{PYFMI_INTEROP_RUNTIME_LIBRARY}}")
    message(FATAL_ERROR "runtime library not found: ${{PYFMI_INTEROP_RUNTIME_LIBRARY}}")
endif()

find_package(Threads REQUIRED)

add_library({model.name} SHARED model_runtime.cpp bindings.cpp)
target_compile_features({model.name} PRIVATE cxx_std_17)
target_include_directories(
    {model.name}
    PRIVATE
    "${{CMAKE_CURRENT_SOURCE_DIR}}"
    "${{PYFMI_INTEROP_RUNTIME_INCLUDE_DIR}}"
)
pyfmi_interop_configure_wire({model.name})

# In protobuf mode the emitted payload schema is compiled here and the generated
# model maps signal values through the resulting message.  Raw mode keeps the
# envelope opaque and does not compile model_wire.cpp.
if(PYFMI_INTEROP_WIRE_MODE STREQUAL "protobuf")
    target_sources({model.name} PRIVATE model_wire.cpp)
    pyfmi_interop_wire_add_proto(
        {model.name}
        "${{CMAKE_CURRENT_SOURCE_DIR}}/{proto_name}"
    )

    add_executable(wire_conformance wire_conformance.cpp)
    target_compile_features(wire_conformance PRIVATE cxx_std_17)
    target_include_directories(
        wire_conformance
        PRIVATE
        "${{CMAKE_CURRENT_SOURCE_DIR}}"
        "${{PYFMI_INTEROP_RUNTIME_INCLUDE_DIR}}"
    )
    target_link_libraries(wire_conformance PRIVATE {model.name})
endif()

# Whole-archive keeps every runtime object, including the FMI facade and the
# weak default model factory, in the packaged model library.
if(MSVC)
    target_link_options(
        {model.name}
        PRIVATE
        "/WHOLEARCHIVE:${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
    )
elseif(APPLE)
    target_link_libraries(
        {model.name}
        PRIVATE
        "-Wl,-force_load,${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
        Threads::Threads
    )
else()
    target_link_libraries(
        {model.name}
        PRIVATE
        "-Wl,--whole-archive"
        "${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
        "-Wl,--no-whole-archive"
        Threads::Threads
    )
endif()

set_target_properties(
    {model.name}
    PROPERTIES
    OUTPUT_NAME "{model.name}"
    POSITION_INDEPENDENT_CODE ON
)
"""
