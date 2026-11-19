"""CMake project text for a generated model.

The generated project is deliberately thin: it compiles the generated
translation units, links the reusable static runtime, and exposes the runtime
locations as cache variables.  Only the protobuf backend contributes a payload
translation unit and a compiled schema; packed and opaque trees compile the
runtime and bindings alone.
"""

from __future__ import annotations

from ..ir import ModelDefinition
from ..roles import derive_role
from ..serialization.protobuf import proto_filename

__all__ = ["render_cmake"]


def render_cmake(model: ModelDefinition, serialization: str = "protobuf") -> str:
    """Return a deterministic ``CMakeLists.txt`` for ``model``."""

    role = model.role or derive_role(model)
    proto_name = proto_filename(model)
    wire_sources = ""
    if serialization == "protobuf":
        wire_sources = f"""
# The protobuf backend compiles its emitted schema and the generated payload
# mapping, and builds a conformance executable from the same model.
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
"""
    elif serialization == "packed":
        wire_sources = f"""
# The packed backend compiles its generated codec and a conformance executable;
# it needs no protobuf schema or library.
target_sources({model.name} PRIVATE model_wire.cpp)

add_executable(wire_conformance wire_conformance.cpp)
target_compile_features(wire_conformance PRIVATE cxx_std_17)
target_include_directories(
    wire_conformance
    PRIVATE
    "${{CMAKE_CURRENT_SOURCE_DIR}}"
    "${{PYFMI_INTEROP_RUNTIME_INCLUDE_DIR}}"
)
target_link_libraries(wire_conformance PRIVATE {model.name})
"""
    else:
        wire_sources = f"""
# The '{serialization}' backend emits no native payload translation unit here;
# this model compiles the runtime ABI and the generated bindings only.
"""

    # A role model opens a transport, so the backends' static initializers must
    # survive the archive link.  A `none` model has no codec and no transport.
    transport_config = ""
    transport_include = ""
    transport_msvc = ""
    transport_apple = ""
    transport_gnu = ""
    if role != "none":
        transport_config = f"""
# This model has wire role "{role}", so the generated codec opens a transport.
# A static backend registers itself from a static initializer; the archive must
# be linked whole or the registration (and the backend) is dropped.
if(NOT PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR)
    message(
        FATAL_ERROR
        "PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR is required for a model with role \\"{role}\\""
    )
endif()
if(NOT PYFMI_INTEROP_TRANSPORT_LIBRARY)
    message(
        FATAL_ERROR
        "PYFMI_INTEROP_TRANSPORT_LIBRARY is required for a model with role \\"{role}\\""
    )
endif()
if(NOT EXISTS "${{PYFMI_INTEROP_TRANSPORT_LIBRARY}}")
    message(
        FATAL_ERROR
        "transport library not found: ${{PYFMI_INTEROP_TRANSPORT_LIBRARY}}"
    )
endif()
"""
        transport_include = f"""
target_include_directories(
    {model.name}
    PRIVATE
    "${{PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR}}"
)
"""
        transport_msvc = (
            '        "/WHOLEARCHIVE:${PYFMI_INTEROP_TRANSPORT_LIBRARY}"\n'
        )
        transport_apple = (
            '        "-Wl,-force_load,${PYFMI_INTEROP_TRANSPORT_LIBRARY}"\n'
        )
        transport_gnu = (
            '        "-Wl,--whole-archive"\n'
            '        "${PYFMI_INTEROP_TRANSPORT_LIBRARY}"\n'
            '        "-Wl,--no-whole-archive"\n'
        )

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
set(
    PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR
    ""
    CACHE PATH
    "Directory containing pyfmi_interop/transport/*.hpp"
)
set(
    PYFMI_INTEROP_TRANSPORT_LIBRARY
    ""
    CACHE FILEPATH
    "Path to the static pyfmi-interop transport library"
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
{transport_config}
find_package(Threads REQUIRED)

add_library({model.name} SHARED model_runtime.cpp bindings.cpp)
target_compile_features({model.name} PRIVATE cxx_std_17)
target_include_directories(
    {model.name}
    PRIVATE
    "${{CMAKE_CURRENT_SOURCE_DIR}}"
    "${{PYFMI_INTEROP_RUNTIME_INCLUDE_DIR}}"
)
{transport_include}pyfmi_interop_configure_wire({model.name})
{wire_sources}
# Whole-archive keeps every runtime object, including the FMI facade and the
# weak default model factory, in the packaged model library.
if(MSVC)
    target_link_options(
        {model.name}
        PRIVATE
        "/WHOLEARCHIVE:${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
{transport_msvc}    )
elseif(APPLE)
    target_link_libraries(
        {model.name}
        PRIVATE
        "-Wl,-force_load,${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
{transport_apple}        Threads::Threads
    )
else()
    target_link_libraries(
        {model.name}
        PRIVATE
        "-Wl,--whole-archive"
        "${{PYFMI_INTEROP_RUNTIME_LIBRARY}}"
        "-Wl,--no-whole-archive"
{transport_gnu}        Threads::Threads
    )
endif()

set_target_properties(
    {model.name}
    PROPERTIES
    OUTPUT_NAME "{model.name}"
    POSITION_INDEPENDENT_CODE ON
)
"""
