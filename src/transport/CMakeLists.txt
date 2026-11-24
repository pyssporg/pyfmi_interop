add_library(pyfmi_interop_transport STATIC
    src/transport_uri.cpp
    src/udp_transport.cpp
    src/tcp_transport.cpp
    src/unix_transport.cpp
)

target_include_directories(pyfmi_interop_transport
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(pyfmi_interop_transport PUBLIC pyfmi_interop_runtime)
target_compile_features(pyfmi_interop_transport PUBLIC cxx_std_17)
set_target_properties(pyfmi_interop_transport PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(pyfmi_interop_transport PRIVATE -Wall -Wextra)
endif()

# The runtime subdirectory is configured first and links this archive through a
# generator expression, which does not create a build dependency by itself.
foreach(consumer pyfmi_interop_fmi2_cs pyfmi_interop_transport_test)
    if(TARGET ${consumer})
        add_dependencies(${consumer} pyfmi_interop_transport)
    endif()
endforeach()
