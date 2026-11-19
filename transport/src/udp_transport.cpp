#include "pyfmi_interop/transport/udp_transport.hpp"

#include "pyfmi_interop/transport/socket_platform.hpp"
#include "pyfmi_interop/transport/transport_uri.hpp"

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#if defined(_WIN32)
#error "pyfmi_interop UDP transport: a Winsock backend is not implemented yet"
#else

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

namespace pyfmi_interop {
namespace transport {
namespace {

constexpr std::size_t kMaxDatagram = 65507;
constexpr int kReceiveBufferBytes = 1 << 20;

sockaddr_in make_address(const Endpoint& endpoint) {
    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(endpoint.port);
    if (endpoint.host.empty() || endpoint.host == "*") {
        address.sin_addr.s_addr = htonl(INADDR_ANY);
        return address;
    }
    if (endpoint.host.find(':') != std::string::npos) {
        throw TransportError("udp transport: IPv6 endpoints are not supported: " +
                             endpoint.host);
    }
    if (::inet_pton(AF_INET, endpoint.host.c_str(), &address.sin_addr) != 1) {
        throw TransportError("udp transport: cannot resolve host '" + endpoint.host + "'");
    }
    return address;
}

void set_non_blocking(detail::socket_handle socket) {
    const int flags = ::fcntl(socket, F_GETFL, 0);
    if (flags < 0 || ::fcntl(socket, F_SETFL, flags | O_NONBLOCK) < 0) {
        throw TransportError("udp transport: cannot set O_NONBLOCK");
    }
}

}  // namespace

struct UdpTransport::Impl {
    detail::socket_handle socket = detail::kInvalidSocket;
    sockaddr_in peer {};
    bool has_peer = false;
    sockaddr_in sender {};
    bool has_sender = false;
    std::uint16_t bound_port = 0;
    std::vector<std::byte> recv_buffer;
    std::optional<std::vector<std::byte>> newest;
};

UdpTransport::UdpTransport() : impl_(std::make_unique<Impl>()) {}

UdpTransport::~UdpTransport() {
    finalize();
}

void UdpTransport::initialize(const std::string& uri) {
    finalize();

    const Uri parsed = parse_uri(uri);
    if (parsed.scheme != "udp") {
        throw TransportError("udp transport: URI scheme is '" + parsed.scheme +
                             "', expected 'udp'");
    }

    impl_->socket = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("udp transport: socket() failed: " +
                             std::string(std::strerror(errno)));
    }

    const int reuse = 1;
    (void)::setsockopt(impl_->socket, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    int receive_buffer = kReceiveBufferBytes;
    (void)::setsockopt(impl_->socket, SOL_SOCKET, SO_RCVBUF, &receive_buffer,
                       sizeof(receive_buffer));

    const sockaddr_in bind_address = make_address(parsed.bind);
    if (::bind(impl_->socket, reinterpret_cast<const sockaddr*>(&bind_address),
               sizeof(bind_address)) != 0) {
        const std::string message =
            "udp transport: bind to " + parsed.bind.host + ":" +
            std::to_string(parsed.bind.port) + " failed: " + std::strerror(errno);
        finalize();
        throw TransportError(message);
    }
    set_non_blocking(impl_->socket);

    sockaddr_in local {};
    socklen_t local_size = sizeof(local);
    if (::getsockname(impl_->socket, reinterpret_cast<sockaddr*>(&local), &local_size) == 0) {
        impl_->bound_port = ntohs(local.sin_port);
    }

    if (parsed.has_peer()) {
        impl_->peer = make_address(*parsed.peer);
        impl_->has_peer = true;
    }

    impl_->recv_buffer.resize(65536);
    impl_->newest.reset();
    impl_->has_sender = false;
    stats_ = {};
}

void UdpTransport::finalize() {
    if (impl_->socket != detail::kInvalidSocket) {
        (void)::close(impl_->socket);
        impl_->socket = detail::kInvalidSocket;
    }
    impl_->has_peer = false;
    impl_->has_sender = false;
    impl_->newest.reset();
}

bool UdpTransport::send(ByteSpan frame) {
    if (frame.size() > kMaxDatagram) {
        throw TransportError("udp transport: frame of " + std::to_string(frame.size()) +
                             " bytes exceeds the 65507-byte datagram limit");
    }
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("udp transport: send before initialize()");
    }

    const sockaddr_in* destination = nullptr;
    if (impl_->has_peer) {
        destination = &impl_->peer;
    } else if (impl_->has_sender) {
        destination = &impl_->sender;
    } else {
        return false;  // No peer configured and no sender observed yet.
    }

    const ssize_t written = ::sendto(
        impl_->socket, frame.data(), frame.size(), 0,
        reinterpret_cast<const sockaddr*>(destination), sizeof(sockaddr_in));
    if (written < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return false;
        }
        if (errno == EMSGSIZE) {
            throw TransportError("udp transport: frame exceeds the path MTU");
        }
        throw TransportError("udp transport: sendto failed: " +
                             std::string(std::strerror(errno)));
    }
    ++stats_.frames_sent;
    return true;
}

std::optional<std::vector<std::byte>> UdpTransport::receive() {
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("udp transport: receive before initialize()");
    }

    for (;;) {
        sockaddr_in from {};
        socklen_t from_size = sizeof(from);
        const ssize_t count = ::recvfrom(
            impl_->socket, impl_->recv_buffer.data(), impl_->recv_buffer.size(), 0,
            reinterpret_cast<sockaddr*>(&from), &from_size);
        if (count < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break;
            }
            throw TransportError("udp transport: recvfrom failed: " +
                                 std::string(std::strerror(errno)));
        }
        impl_->sender = from;
        impl_->has_sender = true;
        if (impl_->newest) {
            ++stats_.dropped_stale;
        }
        impl_->newest.emplace(impl_->recv_buffer.begin(),
                              impl_->recv_buffer.begin() + count);
    }

    if (!impl_->newest) {
        return std::nullopt;
    }
    std::vector<std::byte> frame = std::move(*impl_->newest);
    impl_->newest.reset();
    ++stats_.frames_received;
    return frame;
}

std::uint16_t UdpTransport::bound_port() const noexcept {
    return impl_->bound_port;
}

namespace {
const bool kUdpRegistered = register_transport(
    "udp", []() -> std::unique_ptr<Transport> {
        return std::make_unique<UdpTransport>();
    });
}

}  // namespace transport
}  // namespace pyfmi_interop

#endif  // _WIN32
