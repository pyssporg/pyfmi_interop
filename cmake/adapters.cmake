# Protocol adapter dependency resolution.
#
# One function per adapter, dispatched by `pyfmi_dist_configure_adapter`.  The
# rule is always the same:
#
#   1. use an installed package discovered by find_package() (vcpkg or system),
#   2. else use a checkout under third_party/ when submodules are enabled,
#   3. else fetch the pinned upstream revision when PYFMI_DIST_ALLOW_FETCH=ON,
#   4. else fail with the exact upstream URL and acquisition instructions.
#
# A missing protocol library must never be silently replaced by a stub when the
# adapter gate is ON: a half-adapter that compiles is worse than a build error.

include_guard(GLOBAL)

include(FetchContent)

option(
    PYFMI_DIST_USE_SUBMODULES
    "Prefer third_party/<lib> checkouts over downloading adapter sources"
    ON
)
option(
    PYFMI_DIST_ALLOW_FETCH
    "Allow FetchContent to download pinned adapter sources"
    OFF
)

set(
    PYFMI_DIST_SOURCE_DIR
    "${CMAKE_CURRENT_LIST_DIR}/.."
    CACHE PATH
    "pyfmi_distributed source root (contains third_party/ and cmake/)"
)
set(
    PYFMI_DIST_THIRD_PARTY_DIR
    "${PYFMI_DIST_SOURCE_DIR}/third_party"
    CACHE PATH
    "Directory holding pinned adapter library checkouts"
)

function(pyfmi_dist_fail_missing adapter name url tag mode)
    message(
        FATAL_ERROR
        "${adapter}: ${name} was not found.\n"
        "  acquisition: ${mode}\n"
        "  upstream:    ${url}\n"
        "  pin:         ${tag}\n"
        "Use one of:\n"
        "  - vcpkg (set CMAKE_TOOLCHAIN_FILE and install the port),\n"
        "  - git submodule add ${url} ${PYFMI_DIST_THIRD_PARTY_DIR}/${name},\n"
        "  - configure with -DPYFMI_DIST_ALLOW_FETCH=ON."
    )
endfunction()

function(pyfmi_dist_resolve_source name url tag out_var)
    set(source_dir "${PYFMI_DIST_THIRD_PARTY_DIR}/${name}")

    if(PYFMI_DIST_USE_SUBMODULES AND EXISTS "${source_dir}/CMakeLists.txt")
        get_property(added GLOBAL PROPERTY PYFMI_DIST_ADDED_${name})
        if(NOT added)
            set_property(GLOBAL PROPERTY PYFMI_DIST_ADDED_${name} TRUE)
            add_subdirectory("${source_dir}" "${CMAKE_BINARY_DIR}/_deps/${name}")
        endif()
        set(${out_var} "${source_dir}" PARENT_SCOPE)
        return()
    endif()

    if(PYFMI_DIST_ALLOW_FETCH)
        get_property(added GLOBAL PROPERTY PYFMI_DIST_ADDED_${name})
        if(NOT added)
            set_property(GLOBAL PROPERTY PYFMI_DIST_ADDED_${name} TRUE)
            FetchContent_Declare(
                ${name}
                GIT_REPOSITORY "${url}"
                GIT_TAG "${tag}"
                # Pins include commit SHAs (OpenRTI), which a shallow clone
                # cannot resolve. Fetch the full history only when the operator
                # explicitly opted into downloads.
                GIT_SHALLOW FALSE
            )
            FetchContent_MakeAvailable(${name})
        endif()
        set(${out_var} "${${name}_SOURCE_DIR}" PARENT_SCOPE)
        return()
    endif()

    set(${out_var} "" PARENT_SCOPE)
endfunction()

function(pyfmi_dist_mark target adapter)
    string(TOUPPER "${adapter}" upper)
    target_compile_definitions(${target} PRIVATE PYFMI_DIST_HAVE_${upper}=1)
    target_link_libraries(${target} PUBLIC ${ARGN})
    message(STATUS "pyfmi-distributed: adapter '${adapter}' enabled (${ARGN})")
endfunction()

# --- DIS: open-dis-cpp (vcpkg port exists) ---------------------------------
function(pyfmi_dist_add_dis target)
    find_package(OpenDIS CONFIG QUIET)
    if(OpenDIS_FOUND)
        if(TARGET OpenDIS::OpenDIS7)
            pyfmi_dist_mark(${target} dis OpenDIS::OpenDIS7)
        elseif(TARGET OpenDIS7)
            pyfmi_dist_mark(${target} dis OpenDIS7)
        else()
            message(FATAL_ERROR "OpenDIS was found but exports no DIS7 target")
        endif()
        return()
    endif()

    pyfmi_dist_resolve_source(
        open-dis-cpp
        "https://github.com/open-dis/open-dis-cpp"
        "v1.2.0"
        source_dir
    )
    if(NOT source_dir)
        pyfmi_dist_fail_missing(
            "dis" "open-dis-cpp"
            "https://github.com/open-dis/open-dis-cpp" "v1.2.0" "vcpkg"
        )
    endif()
    set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    if(TARGET OpenDIS::OpenDIS7)
        pyfmi_dist_mark(${target} dis OpenDIS::OpenDIS7)
    elseif(TARGET OpenDIS7)
        pyfmi_dist_mark(${target} dis OpenDIS7)
    else()
        message(FATAL_ERROR "open-dis-cpp produced no DIS7 target")
    endif()
endfunction()

# --- HLA: OpenRTI (pkg-config / in-tree targets, no CMake package config) ---
# OpenRTI assumes it is the top-level project: its subdirectory CMake files use
# CMAKE_SOURCE_DIR and its top level unconditionally adds its tests.  Embedding
# the checkout with add_subdirectory() therefore fails.  We prepare a build-tree
# copy with CMAKE_SOURCE_DIR rewritten to CMAKE_CURRENT_SOURCE_DIR and the test
# subtree removed, then add that copy.  The submodule stays pristine.
function(pyfmi_dist_prepare_openrti source_dir out_var)
    set(patched "${CMAKE_BINARY_DIR}/_deps/OpenRTI-src")
    file(COPY "${source_dir}/" DESTINATION "${patched}" PATTERN ".git" EXCLUDE)

    file(GLOB_RECURSE cmake_files
        "${patched}/CMakeLists.txt"
        "${patched}/*.cmake"
    )
    foreach(cmake_file IN LISTS cmake_files)
        file(READ "${cmake_file}" contents)
        string(REPLACE "CMAKE_SOURCE_DIR" "PYFMI_DIST_OPENRTI_ROOT" contents "${contents}")
        string(REPLACE "CMAKE_BINARY_DIR" "PYFMI_DIST_OPENRTI_BINARY_DIR" contents "${contents}")
        file(WRITE "${cmake_file}" "${contents}")
    endforeach()

    set(top "${patched}/CMakeLists.txt")
    file(READ "${top}" contents)
    string(REPLACE "add_subdirectory(tests)" "# tests disabled by pyfmi-distributed" contents "${contents}")
    file(WRITE "${top}" "${contents}")

    set(${out_var} "${patched}" PARENT_SCOPE)
endfunction()

function(pyfmi_dist_add_hla target)
    find_package(OpenRTI CONFIG QUIET)
    if(TARGET rti1516e)
        pyfmi_dist_mark(${target} hla rti1516e)
        return()
    endif()

    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
        pkg_check_modules(RTI1516E QUIET rti1516e)
        if(RTI1516E_FOUND)
            target_include_directories(${target} PRIVATE ${RTI1516E_INCLUDE_DIRS})
            target_link_directories(${target} PRIVATE ${RTI1516E_LIBRARY_DIRS})
            pyfmi_dist_mark(${target} hla ${RTI1516E_LIBRARIES})
            return()
        endif()
    endif()

    set(source_dir "${PYFMI_DIST_THIRD_PARTY_DIR}/OpenRTI")
    if(NOT (PYFMI_DIST_USE_SUBMODULES AND EXISTS "${source_dir}/CMakeLists.txt"))
        if(NOT PYFMI_DIST_ALLOW_FETCH)
            pyfmi_dist_fail_missing(
                "hla" "OpenRTI"
                "https://github.com/onox/OpenRTI" "fb454e6"
                "submodule or FetchContent"
            )
        endif()
        get_property(added GLOBAL PROPERTY PYFMI_DIST_ADDED_OpenRTI)
        if(NOT added)
            set_property(GLOBAL PROPERTY PYFMI_DIST_ADDED_OpenRTI TRUE)
            FetchContent_Declare(
                OpenRTI
                GIT_REPOSITORY "https://github.com/onox/OpenRTI"
                GIT_TAG "fb454e6"
                GIT_SHALLOW FALSE
            )
            FetchContent_Populate(OpenRTI)
        endif()
        set(source_dir "${OpenRTI_SOURCE_DIR}")
    endif()

    pyfmi_dist_prepare_openrti("${source_dir}" patched_dir)
    set(OPENRTI_BUILD_SHARED OFF CACHE BOOL "" FORCE)
    set(OPENRTI_ENABLE_PYTHON_BINDINGS OFF CACHE BOOL "" FORCE)
    set(OPENRTI_ENABLE_RTI13 OFF CACHE BOOL "" FORCE)
    set(OPENRTI_ENABLE_RTI1516 OFF CACHE BOOL "" FORCE)
    set(OPENRTI_ENABLE_RTI1516E ON CACHE BOOL "" FORCE)
    set(PYFMI_DIST_OPENRTI_ROOT "${patched_dir}")
    set(PYFMI_DIST_OPENRTI_BINARY_DIR "${CMAKE_BINARY_DIR}/_deps/OpenRTI-build")
    add_subdirectory("${patched_dir}" "${PYFMI_DIST_OPENRTI_BINARY_DIR}")
    target_include_directories(
        ${target} PRIVATE
        "${patched_dir}/include"
        "${patched_dir}/include/rti1516e"
    )
    pyfmi_dist_mark(${target} hla rti1516e)
endfunction()

# --- DCP: ASAM X-DCP via DCPLib --------------------------------------------
function(pyfmi_dist_add_dcp target)
    find_package(DCPLib CONFIG QUIET)
    if(DCPLib_FOUND)
        pyfmi_dist_mark(
            ${target} dcp
            DCPLib::Core DCPLib::Slave DCPLib::Master DCPLib::Ethernet
        )
        return()
    endif()

    pyfmi_dist_resolve_source(
        DCPLib
        "https://github.com/modelica/DCPLib"
        "v0.2"
        source_dir
    )
    if(NOT source_dir)
        pyfmi_dist_fail_missing(
            "dcp" "DCPLib"
            "https://github.com/modelica/DCPLib" "v0.2" "submodule or FetchContent"
        )
    endif()
    # DCPLib looks for ASIO::ASIO while vcpkg's asio port exports asio::asio.
    if(TARGET asio::asio AND NOT TARGET ASIO::ASIO)
        add_library(ASIO::ASIO INTERFACE IMPORTED)
        target_link_libraries(ASIO::ASIO INTERFACE asio::asio)
    endif()
    set(BUILD_ALL ON CACHE BOOL "" FORCE)
    set(BUILD_ETHERNET ON CACHE BOOL "" FORCE)
    set(BUILD_SLAVE ON CACHE BOOL "" FORCE)
    set(BUILD_MASTER ON CACHE BOOL "" FORCE)
    set(BUILD_XML ON CACHE BOOL "" FORCE)
    set(BUILD_ZIP ON CACHE BOOL "" FORCE)
    # DCPLib builds its own `mytest` executable unconditionally.  It is not part
    # of the adapter and pulls in libzip's transitive crypto/compression libs,
    # so keep it out of the default build.
    if(TARGET mytest)
        set_target_properties(mytest PROPERTIES EXCLUDE_FROM_ALL TRUE)
    endif()
    pyfmi_dist_mark(
        ${target} dcp
        DCPLib::Core DCPLib::Slave DCPLib::Master DCPLib::Ethernet
    )
endfunction()

# --- ED-247: Airbus ED247_LIBRARY ------------------------------------------
function(pyfmi_dist_add_ed247 target)
    find_package(Ed247 CONFIG QUIET)
    if(TARGET Ed247::static)
        pyfmi_dist_mark(${target} ed247 Ed247::static)
        return()
    endif()

    pyfmi_dist_resolve_source(
        ED247_LIBRARY
        "https://github.com/airbus/ED247_LIBRARY"
        "VA2.3.0"
        source_dir
    )
    if(NOT source_dir)
        pyfmi_dist_fail_missing(
            "ed247" "ED247_LIBRARY"
            "https://github.com/airbus/ED247_LIBRARY" "VA2.3.0"
            "submodule or FetchContent"
        )
    endif()
    if(TARGET Ed247::static)
        pyfmi_dist_mark(${target} ed247 Ed247::static)
    elseif(TARGET ed247_static)
        pyfmi_dist_mark(${target} ed247 ed247_static)
    else()
        message(FATAL_ERROR "ED247_LIBRARY produced no static target")
    endif()
    # ED247_LIBRARY VA2.3.0 uses std::numeric_limits without including <limits>,
    # which newer libstdc++ no longer pulls in transitively.  Force-include the
    # header for the library's own objects instead of patching the submodule.
    if(TARGET ed247_objects)
        if(MSVC)
            target_compile_options(ed247_objects PRIVATE /FIlimits)
        else()
            target_compile_options(ed247_objects PRIVATE -include limits)
        endif()
    endif()
endfunction()

# --- ROS 2: system installation only ---------------------------------------
function(pyfmi_dist_add_ros2 target)
    find_package(rclcpp REQUIRED)
    pyfmi_dist_mark(${target} ros2 rclcpp::rclcpp)
endfunction()

function(pyfmi_dist_configure_adapter adapter target)
    if(adapter STREQUAL "hla")
        pyfmi_dist_add_hla(${target})
    elseif(adapter STREQUAL "dis")
        pyfmi_dist_add_dis(${target})
    elseif(adapter STREQUAL "dcp")
        pyfmi_dist_add_dcp(${target})
    elseif(adapter STREQUAL "ros2")
        pyfmi_dist_add_ros2(${target})
    elseif(adapter STREQUAL "ed247")
        pyfmi_dist_add_ed247(${target})
    else()
        message(FATAL_ERROR "unknown adapter '${adapter}'")
    endif()
endfunction()
