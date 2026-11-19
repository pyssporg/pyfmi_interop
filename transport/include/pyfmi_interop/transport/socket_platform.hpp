#pragma once

// Keeps the transport headers portable: POSIX is the reference implementation,
// and a Winsock backend can be added behind the same public headers.
#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <sys/socket.h>
#include <sys/types.h>
#endif

namespace pyfmi_interop {
namespace transport {
namespace detail {

#if defined(_WIN32)
using socket_handle = SOCKET;
constexpr socket_handle kInvalidSocket = INVALID_SOCKET;
#else
using socket_handle = int;
constexpr socket_handle kInvalidSocket = -1;
#endif

}  // namespace detail
}  // namespace transport
}  // namespace pyfmi_interop
