set(PYFMI_DIST_RUNTIME_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include)
set(PYFMI_DIST_FMI2_INCLUDE_DIR ${PROJECT_SOURCE_DIR}/third_party/fmi2/headers)

include(${PROJECT_SOURCE_DIR}/cmake/adapters.cmake)

find_package(Threads REQUIRED)

set(PYFMI_DIST_RUNTIME_OPTIONS
    PYFMI_DIST_ENABLE_HLA
    PYFMI_DIST_ENABLE_DIS
    PYFMI_DIST_ENABLE_DCP
    PYFMI_DIST_ENABLE_ROS2
    PYFMI_DIST_ENABLE_ED247
)

# The static runtime owns the FMI facade as well as the reusable runtime so a
# generated model links the complete FMI ABI.  The shared target below is only a
# convenience wrapper that retains every object of this archive.
add_library(pyfmi_distributed_runtime STATIC
    src/model_runtime.cpp
    src/model_factory_default.cpp
    src/transport.cpp
    src/loopback_transport.cpp
    src/scheduler.cpp
    src/fmi2_cs_api.cpp
    src/adapters/hla.cpp
    src/adapters/dis.cpp
    src/adapters/dcp.cpp
    src/adapters/ros2.cpp
    src/adapters/ed247.cpp
)

target_include_directories(pyfmi_distributed_runtime
    PUBLIC
        ${PYFMI_DIST_RUNTIME_INCLUDE_DIR}
        ${PYFMI_DIST_FMI2_INCLUDE_DIR}
)

target_compile_features(pyfmi_distributed_runtime PUBLIC cxx_std_17)
set_target_properties(pyfmi_distributed_runtime PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(pyfmi_distributed_runtime PRIVATE -Wall -Wextra)
endif()

# A shared library needs at least one source.  This deterministic anchor keeps
# the target's own translation unit empty; the actual content is whole-archive
# linked from pyfmi_distributed_runtime.
set(PYFMI_DIST_FMI2_SHARED_ANCHOR
    "${CMAKE_CURRENT_BINARY_DIR}/fmi2_cs_shared_anchor.cpp")
if(NOT EXISTS "${PYFMI_DIST_FMI2_SHARED_ANCHOR}")
    file(WRITE "${PYFMI_DIST_FMI2_SHARED_ANCHOR}"
        "// Anchor translation unit for the convenience shared FMI facade.\n")
endif()

add_library(pyfmi_distributed_fmi2_cs SHARED
    "${PYFMI_DIST_FMI2_SHARED_ANCHOR}"
)

target_include_directories(pyfmi_distributed_fmi2_cs
    PUBLIC
        ${PYFMI_DIST_RUNTIME_INCLUDE_DIR}
        ${PYFMI_DIST_FMI2_INCLUDE_DIR}
)

target_compile_features(pyfmi_distributed_fmi2_cs PUBLIC cxx_std_17)

if(MSVC)
    target_link_options(
        pyfmi_distributed_fmi2_cs
        PRIVATE
        "/WHOLEARCHIVE:$<TARGET_FILE:pyfmi_distributed_runtime>"
    )
elseif(APPLE)
    target_link_libraries(
        pyfmi_distributed_fmi2_cs
        PRIVATE
        "-Wl,-force_load,$<TARGET_FILE:pyfmi_distributed_runtime>"
    )
else()
    target_link_libraries(
        pyfmi_distributed_fmi2_cs
        PRIVATE
        "-Wl,--whole-archive"
        "$<TARGET_FILE:pyfmi_distributed_runtime>"
        "-Wl,--no-whole-archive"
    )
endif()
target_link_libraries(pyfmi_distributed_fmi2_cs PRIVATE Threads::Threads)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(pyfmi_distributed_fmi2_cs PRIVATE -Wall -Wextra)
endif()

# Resolve the protocol libraries for every enabled adapter on both targets.  A
# missing library fails configuration with the message from adapters.cmake; no
# stub is substituted.
foreach(option_name IN LISTS PYFMI_DIST_RUNTIME_OPTIONS)
    if(${option_name})
        string(REPLACE "PYFMI_DIST_ENABLE_" "" adapter_name "${option_name}")
        string(TOLOWER "${adapter_name}" adapter_name)
        target_compile_definitions(pyfmi_distributed_runtime PRIVATE ${option_name}=1)
        pyfmi_dist_configure_adapter(${adapter_name} pyfmi_distributed_runtime)
        pyfmi_dist_configure_adapter(${adapter_name} pyfmi_distributed_fmi2_cs)
    endif()
endforeach()

if(BUILD_TESTING AND PYFMI_DIST_BUILD_TESTS)
    add_executable(pyfmi_distributed_runtime_test
        tests/test_runtime.cpp
    )
    target_link_libraries(pyfmi_distributed_runtime_test PRIVATE pyfmi_distributed_runtime)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(pyfmi_distributed_runtime_test PRIVATE -Wall -Wextra)
    endif()
    add_test(NAME pyfmi_distributed_runtime_test COMMAND pyfmi_distributed_runtime_test)

    add_executable(pyfmi_distributed_fmi2_api_test
        tests/test_fmi2_api.cpp
    )
    target_link_libraries(pyfmi_distributed_fmi2_api_test PRIVATE pyfmi_distributed_fmi2_cs)
    # Export the test's strong model factory so it interposes the weak default
    # definition shipped inside the shared facade.
    set_target_properties(pyfmi_distributed_fmi2_api_test PROPERTIES ENABLE_EXPORTS ON)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(pyfmi_distributed_fmi2_api_test PRIVATE -Wall -Wextra)
    endif()
    add_test(NAME pyfmi_distributed_fmi2_api_test COMMAND pyfmi_distributed_fmi2_api_test)
endif()
