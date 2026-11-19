#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "pyfmi_interop/runtime/transport.hpp"

namespace pyfmi_interop {
namespace transport {

struct Endpoint {
    std::string host;
    std::uint16_t port = 0;
};

// Parsed configuration URI.  Grammar:
//   loopback
//   udp://<bind-host>:<port>[?peer=<host>:<port>]
//   tcp://<bind-host>:<port>[?peer=<host>:<port>]
// A port of 0 asks the OS for an ephemeral port.  The peer form of tcp is
// connect mode; without it the backend listens.
struct Uri {
    std::string scheme;
    Endpoint bind;
    std::optional<Endpoint> peer;

    bool has_peer() const noexcept { return peer.has_value(); }
};

// Throws TransportError with a diagnostic on a malformed URI.
Uri parse_uri(std::string_view uri);

// Scheme part of a bare name or a full URI.
std::string scheme_of(std::string_view name_or_uri);

}  // namespace transport
}  // namespace pyfmi_interop
