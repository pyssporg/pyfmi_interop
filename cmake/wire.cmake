# Wire payload mode for the runtime and generated models.
#
# `PYFMI_INTEROP_WIRE` selects the payload implementation:
#   * `protobuf` — generated models compile their emitted `<Model>.proto` with
#     protoc and map signal values through the generated message;
#   * `raw` — the envelope carries opaque caller bytes, the existing layout.
#
# Leaving the cache variable empty selects `protobuf` when libprotobuf and
# protoc are found, otherwise `raw`.  The resolved value is exposed as the
# `PYFMI_INTEROP_WIRE_MODE` cache variable and as the target property
# `PYFMI_INTEROP_WIRE_MODE`, with the matching `PYFMI_INTEROP_WIRE_PROTOBUF` or
# `PYFMI_INTEROP_WIRE_RAW` compile definition.

include_guard(GLOBAL)

if(NOT DEFINED PYFMI_INTEROP_WIRE)
    set(
        PYFMI_INTEROP_WIRE
        ""
        CACHE STRING
        "Wire payload mode: protobuf or raw (empty selects protobuf when libprotobuf is found)"
    )
endif()

find_package(Protobuf QUIET)

function(pyfmi_interop_resolve_wire)
    if(PYFMI_INTEROP_WIRE STREQUAL "")
        if(Protobuf_FOUND AND Protobuf_PROTOC_EXECUTABLE)
            set(_pyfmi_wire_mode protobuf)
            message(
                STATUS
                "pyfmi_interop: PYFMI_INTEROP_WIRE not set; libprotobuf found, using 'protobuf'"
            )
        else()
            set(_pyfmi_wire_mode raw)
            message(
                STATUS
                "pyfmi_interop: PYFMI_INTEROP_WIRE not set; libprotobuf not found, using 'raw'"
            )
        endif()
    else()
        set(_pyfmi_wire_mode "${PYFMI_INTEROP_WIRE}")
    endif()

    if(NOT _pyfmi_wire_mode MATCHES "^(protobuf|raw)$")
        message(
            FATAL_ERROR
            "PYFMI_INTEROP_WIRE='${_pyfmi_wire_mode}' is invalid; use protobuf or raw"
        )
    endif()
    if(_pyfmi_wire_mode STREQUAL "protobuf")
        if(NOT Protobuf_FOUND OR NOT Protobuf_PROTOC_EXECUTABLE)
            message(
                FATAL_ERROR
                "PYFMI_INTEROP_WIRE=protobuf requires libprotobuf and protoc"
            )
        endif()
    endif()

    set(PYFMI_INTEROP_WIRE_MODE "${_pyfmi_wire_mode}" CACHE STRING
        "Resolved wire payload mode (protobuf or raw)" FORCE)
    message(STATUS "pyfmi_interop: wire payload mode '${_pyfmi_wire_mode}'")
endfunction()

function(pyfmi_interop_configure_wire target)
    if(NOT PYFMI_INTEROP_WIRE_MODE)
        message(FATAL_ERROR "call pyfmi_interop_resolve_wire() before configuring ${target}")
    endif()
    if(PYFMI_INTEROP_WIRE_MODE STREQUAL "protobuf")
        target_compile_definitions(${target} PUBLIC PYFMI_INTEROP_WIRE_PROTOBUF=1)
    else()
        target_compile_definitions(${target} PUBLIC PYFMI_INTEROP_WIRE_RAW=1)
    endif()
    set_target_properties(
        ${target}
        PROPERTIES PYFMI_INTEROP_WIRE_MODE "${PYFMI_INTEROP_WIRE_MODE}"
    )
endfunction()

# Compile `proto` with protoc into a static target linked into `target`.
# Call only in protobuf mode.
function(pyfmi_interop_wire_add_proto target proto)
    if(NOT PYFMI_INTEROP_WIRE_MODE STREQUAL "protobuf")
        message(FATAL_ERROR "pyfmi_interop_wire_add_proto requires protobuf mode")
    endif()
    if(NOT Protobuf_FOUND)
        message(FATAL_ERROR "protobuf mode requires libprotobuf and protoc")
    endif()

    get_filename_component(_pyfmi_proto "${proto}" ABSOLUTE)
    get_filename_component(_pyfmi_proto_dir "${_pyfmi_proto}" DIRECTORY)
    get_filename_component(_pyfmi_proto_name "${_pyfmi_proto}" NAME_WE)
    set(_pyfmi_proto_gen "${CMAKE_CURRENT_BINARY_DIR}/proto")
    file(MAKE_DIRECTORY "${_pyfmi_proto_gen}")

    add_custom_command(
        OUTPUT
            "${_pyfmi_proto_gen}/${_pyfmi_proto_name}.pb.cc"
            "${_pyfmi_proto_gen}/${_pyfmi_proto_name}.pb.h"
        COMMAND
            "${Protobuf_PROTOC_EXECUTABLE}"
            "--cpp_out=${_pyfmi_proto_gen}"
            "-I${_pyfmi_proto_dir}"
            "${_pyfmi_proto}"
        DEPENDS "${_pyfmi_proto}"
        COMMENT "protoc ${_pyfmi_proto_name}.proto"
        VERBATIM
    )

    add_library(${target}_proto STATIC "${_pyfmi_proto_gen}/${_pyfmi_proto_name}.pb.cc")
    target_include_directories(${target}_proto PUBLIC "${_pyfmi_proto_gen}")
    target_link_libraries(${target}_proto PUBLIC protobuf::libprotobuf)
    target_compile_features(${target}_proto PUBLIC cxx_std_17)
    set_target_properties(${target}_proto PROPERTIES POSITION_INDEPENDENT_CODE ON)

    target_link_libraries(${target} PRIVATE ${target}_proto)
endfunction()
