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
# IMPORT_ROOTS lists the additional protoc import roots the proto needs.
# Call only where libprotobuf and protoc are available; the generator gates
# the built-in protobuf target on protobuf mode.
function(pyfmi_interop_wire_add_proto target proto)
    cmake_parse_arguments(PARSE_ARGV 2 _pyfmi_wire "" "" "IMPORT_ROOTS")
    if(NOT Protobuf_FOUND)
        message(FATAL_ERROR "pyfmi_interop_wire_add_proto requires libprotobuf and protoc")
    endif()

    get_filename_component(_pyfmi_proto "${proto}" ABSOLUTE)
    get_filename_component(_pyfmi_proto_dir "${_pyfmi_proto}" DIRECTORY)
    set(_pyfmi_proto_gen "${CMAKE_CURRENT_BINARY_DIR}/proto")
    file(MAKE_DIRECTORY "${_pyfmi_proto_gen}")

    # Declared import roots come first: a proto inside one must keep its
    # root-relative path, so protoc emits `<relative>.pb.{h,cc}` where the
    # codec's `#include` expects it.  The proto's own directory is only a
    # fallback import root, appended last.
    set(_pyfmi_proto_roots "")
    foreach(_pyfmi_root IN LISTS _pyfmi_wire_IMPORT_ROOTS)
        get_filename_component(_pyfmi_root_abs "${_pyfmi_root}" ABSOLUTE)
        list(APPEND _pyfmi_proto_roots "${_pyfmi_root_abs}")
    endforeach()
    list(APPEND _pyfmi_proto_roots "${_pyfmi_proto_dir}")
    list(REMOVE_DUPLICATES _pyfmi_proto_roots)

    set(_pyfmi_proto_include_args "")
    foreach(_pyfmi_root IN LISTS _pyfmi_proto_roots)
        list(APPEND _pyfmi_proto_include_args "-I${_pyfmi_root}")
    endforeach()
    set(_pyfmi_proto_rel "")
    foreach(_pyfmi_root IN LISTS _pyfmi_proto_roots)
        file(RELATIVE_PATH _pyfmi_rel "${_pyfmi_root}" "${_pyfmi_proto}")
        if(NOT _pyfmi_rel MATCHES "^\\.\\.")
            set(_pyfmi_proto_rel "${_pyfmi_rel}")
            break()
        endif()
    endforeach()
    if(_pyfmi_proto_rel STREQUAL "")
        get_filename_component(_pyfmi_proto_rel "${_pyfmi_proto}" NAME)
    endif()

    get_filename_component(_pyfmi_rel_dir "${_pyfmi_proto_rel}" DIRECTORY)
    get_filename_component(_pyfmi_rel_name "${_pyfmi_proto_rel}" NAME_WE)
    if(_pyfmi_rel_dir)
        set(_pyfmi_proto_out "${_pyfmi_proto_gen}/${_pyfmi_rel_dir}")
    else()
        set(_pyfmi_proto_out "${_pyfmi_proto_gen}")
    endif()
    file(MAKE_DIRECTORY "${_pyfmi_proto_out}")

    add_custom_command(
        OUTPUT
            "${_pyfmi_proto_out}/${_pyfmi_rel_name}.pb.cc"
            "${_pyfmi_proto_out}/${_pyfmi_rel_name}.pb.h"
        COMMAND
            "${Protobuf_PROTOC_EXECUTABLE}"
            "--cpp_out=${_pyfmi_proto_gen}"
            ${_pyfmi_proto_include_args}
            "${_pyfmi_proto}"
        DEPENDS "${_pyfmi_proto}"
        COMMENT "protoc ${_pyfmi_rel_name}.proto"
        VERBATIM
    )

    set(_pyfmi_proto_target "${target}_proto")
    if(TARGET "${_pyfmi_proto_target}")
        set(_pyfmi_proto_target "${target}_${_pyfmi_rel_name}_proto")
    endif()

    add_library(
        ${_pyfmi_proto_target}
        STATIC
        "${_pyfmi_proto_out}/${_pyfmi_rel_name}.pb.cc"
    )
    target_include_directories(${_pyfmi_proto_target} PUBLIC "${_pyfmi_proto_gen}")
    target_link_libraries(${_pyfmi_proto_target} PUBLIC protobuf::libprotobuf)
    target_compile_features(${_pyfmi_proto_target} PUBLIC cxx_std_17)
    set_target_properties(
        ${_pyfmi_proto_target}
        PROPERTIES POSITION_INDEPENDENT_CODE ON
    )

    target_link_libraries(${target} PRIVATE ${_pyfmi_proto_target})
    # Linking orders the link step only; the consumer's own sources still
    # compile in parallel with the proto target.  Order the whole build so a
    # cold Ninja pass cannot race the protoc command that produces the header.
    add_dependencies(${target} ${_pyfmi_proto_target})
endfunction()
