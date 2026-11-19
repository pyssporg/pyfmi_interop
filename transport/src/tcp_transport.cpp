#include "pyfmi_interop/transport/tcp_transport.hpp"

#include "pyfmi_interop/transport/socket_platform.hpp"
#include "pyfmi_interop/transport/transport_uri.hpp"

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#if defined(_WIN32)
#error "pyfmi_interop TCP transport: a Winsock backend is not implemented yet"
#else

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

namespace pyfmi_interop {
namespace transport {
namespace {

constexpr std::size_t kWireHeaderSize = 56;
constexpr std::size_t kMaxFramePayload = 64u * 1024u * 1024u;
constexpr std::size_t kMaxQueuedBytes = 4u * 1024u * 1024u;

std::uint16_t read_u16(const std::byte* source) {
    return static_cast<std::uint16_t>(
        std::to_integer<std::uint8_t>(source[0]) |
        (static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(source[1])) << 8u));
}

std::uint32_t read_u32(const std::byte* source) {
    return static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(source[0])) |
           (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(source[1])) << 8u) |
           (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(source[2])) << 16u) |
           (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(source[3])) << 24u);
}

sockaddr_in make_address(const Endpoint& endpoint) {
    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(endpoint.port);
    if (endpoint.host.empty() || endpoint.host == "*") {
        address.sin_addr.s_addr = htonl(INADDR_ANY);
        return address;
    }
    if (endpoint.host.find(':') != std::string::npos) {
        throw TransportError("tcp transport: IPv6 endpoints are not supported: " +
                             endpoint.host);
    }
    if (::inet_pton(AF_INET, endpoint.host.c_str(), &address.sin_addr) != 1) {
        throw TransportError("tcp transport: cannot resolve host '" + endpoint.host + "'");
    }
    return address;
}

void set_non_blocking(detail::socket_handle socket) {
    const int flags = ::fcntl(socket, F_GETFL, 0);
    if (flags < 0 || ::fcntl(socket, F_SETFL, flags | O_NONBLOCK) < 0) {
        throw TransportError("tcp transport: cannot set O_NONBLOCK");
    }
}

}  // namespace

struct TcpTransport::Impl {
    detail::socket_handle listener = detail::kInvalidSocket;
    detail::socket_handle peer = detail::kInvalidSocket;
    bool connect_mode = false;
    bool connecting = false;
    sockaddr_in peer_address {};
    std::uint16_t bound_port = 0;
    std::vector<std::byte> receive_buffer;
    std::vector<std::byte> rx_buffer;
    std::optional<std::vector<std::byte>> newest;
    std::deque<std::vector<std::byte>> send_queue;
    std::size_t send_offset = 0;
    std::size_t queued_bytes = 0;
};

TcpTransport::TcpTransport() : impl_(std::make_unique<Impl>()) {}

TcpTransport::~TcpTransport() {
    finalize();
}

void TcpTransport::initialize(const std::string& uri) {
    finalize();

    const Uri parsed = parse_uri(uri);
    if (parsed.scheme != "tcp") {
        throw TransportError("tcp transport: URI scheme is '" + parsed.scheme +
                             "', expected 'tcp'");
    }

    impl_->listener = ::socket(AF_INET, SOCK_STREAM, 0);
    if (impl_->listener == detail::kInvalidSocket) {
        throw TransportError("tcp transport: socket() failed: " +
                             std::string(std::strerror(errno)));
    }
    const int reuse = 1;
    (void)::setsockopt(impl_->listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    const sockaddr_in bind_address = make_address(parsed.bind);
    if (::bind(impl_->listener, reinterpret_cast<const sockaddr*>(&bind_address),
               sizeof(bind_address)) != 0) {
        const std::string message =
            "tcp transport: bind to " + parsed.bind.host + ":" +
            std::to_string(parsed.bind.port) + " failed: " + std::strerror(errno);
        finalize();
        throw TransportError(message);
    }
    set_non_blocking(impl_->listener);

    sockaddr_in local {};
    socklen_t local_size = sizeof(local);
    if (::getsockname(impl_->listener, reinterpret_cast<sockaddr*>(&local), &local_size) == 0) {
        impl_->bound_port = ntohs(local.sin_port);
    }

    impl_->connect_mode = parsed.has_peer();
    if (impl_->connect_mode) {
        impl_->peer_address = make_address(*parsed.peer);
    } else if (::listen(impl_->listener, 1) != 0) {
        const std::string message =
            "tcp transport: listen failed: " + std::string(std::strerror(errno));
        finalize();
        throw TransportError(message);
    }

    impl_->receive_buffer.resize(65536);
    stats_ = {};
}

void TcpTransport::finalize() {
    if (impl_->peer != detail::kInvalidSocket) {
        (void)::close(impl_->peer);
        impl_->peer = detail::kInvalidSocket;
    }
    if (impl_->listener != detail::kInvalidSocket) {
        (void)::close(impl_->listener);
        impl_->listener = detail::kInvalidSocket;
    }
    impl_->connect_mode = false;
    impl_->connecting = false;
    impl_->receive_buffer.clear();
    impl_->rx_buffer.clear();
    impl_->newest.reset();
    impl_->send_queue.clear();
    impl_->send_offset = 0;
    impl_->queued_bytes = 0;
}

std::uint16_t TcpTransport::bound_port() const noexcept {
    return impl_->bound_port;
}

namespace {

bool finish_connect(TcpTransport::Impl& impl) {
    if (!impl.connecting) {
        return impl.peer != detail::kInvalidSocket;
    }
    pollfd descriptor {};
    descriptor.fd = impl.peer;
    descriptor.events = POLLOUT;
    const int ready = ::poll(&descriptor, 1, 0);
    if (ready <= 0) {
        return false;
    }
    int error = 0;
    socklen_t error_size = sizeof(error);
    if (::getsockopt(impl.peer, SOL_SOCKET, SO_ERROR, &error, &error_size) != 0 ||
        error != 0) {
        (void)::close(impl.peer);
        impl.peer = detail::kInvalidSocket;
        impl.connecting = false;
        return false;
    }
    impl.connecting = false;
    return true;
}

void disable_nagle(detail::socket_handle socket) {
    const int enabled = 1;
    (void)::setsockopt(socket, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled));
}

bool ensure_connected(TcpTransport::Impl& impl);

bool accept_peer(TcpTransport::Impl& impl) {
    if (impl.listener == detail::kInvalidSocket) {
        return false;
    }
    for (;;) {
        sockaddr_in remote {};
        socklen_t remote_size = sizeof(remote);
        const detail::socket_handle accepted =
            ::accept(impl.listener, reinterpret_cast<sockaddr*>(&remote), &remote_size);
        if (accepted == detail::kInvalidSocket) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                return impl.peer != detail::kInvalidSocket;
            }
            throw TransportError("tcp transport: accept failed: " +
                                 std::string(std::strerror(errno)));
        }
        if (impl.peer != detail::kInvalidSocket) {
            (void)::close(accepted);  // One peer at a time.
            continue;
        }
        set_non_blocking(accepted);
        disable_nagle(accepted);
        impl.peer = accepted;
        return true;
    }
}

bool ensure_connected(TcpTransport::Impl& impl) {
    if (impl.peer != detail::kInvalidSocket) {
        return finish_connect(impl);
    }
    if (!impl.connect_mode) {
        return accept_peer(impl);
    }

    impl.peer = ::socket(AF_INET, SOCK_STREAM, 0);
    if (impl.peer == detail::kInvalidSocket) {
        throw TransportError("tcp transport: socket() failed: " +
                             std::string(std::strerror(errno)));
    }
    set_non_blocking(impl.peer);
    disable_nagle(impl.peer);
    if (::connect(impl.peer, reinterpret_cast<const sockaddr*>(&impl.peer_address),
                  sizeof(impl.peer_address)) == 0) {
        return true;
    }
    if (errno == EINPROGRESS) {
        impl.connecting = true;
        return finish_connect(impl);
    }
    const std::string message =
        "tcp transport: connect failed: " + std::string(std::strerror(errno));
    (void)::close(impl.peer);
    impl.peer = detail::kInvalidSocket;
    throw TransportError(message);
}

void disconnect_peer(TcpTransport::Impl& impl) {
    if (impl.peer != detail::kInvalidSocket) {
        (void)::close(impl.peer);
        impl.peer = detail::kInvalidSocket;
    }
    impl.connecting = false;
    impl.rx_buffer.clear();
}

void flush_send_queue(TcpTransport::Impl& impl, TransportStats& stats) {
    while (impl.peer != detail::kInvalidSocket && !impl.send_queue.empty()) {
        std::vector<std::byte>& front = impl.send_queue.front();
        const std::size_t remaining = front.size() - impl.send_offset;
        const ssize_t written = ::send(impl.peer, front.data() + impl.send_offset,
                                       remaining, MSG_NOSIGNAL);
        if (written < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                return;
            }
            disconnect_peer(impl);
            return;
        }
        if (written == 0) {
            return;
        }
        impl.send_offset += static_cast<std::size_t>(written);
        impl.queued_bytes -= static_cast<std::size_t>(written);
        if (impl.send_offset == front.size()) {
            impl.send_queue.pop_front();
            impl.send_offset = 0;
            ++stats.frames_sent;
        }
    }
}

void extract_frames(TcpTransport::Impl& impl, TransportStats& stats) {
    for (;;) {
        if (impl.rx_buffer.size() < kWireHeaderSize) {
            return;
        }
        const std::byte* header = impl.rx_buffer.data();
        if (read_u16(header + 6) != kWireHeaderSize) {
            ++stats.format_errors;
            impl.rx_buffer.clear();
            disconnect_peer(impl);
            return;
        }
        const std::uint32_t payload_length = read_u32(header + 36);
        if (payload_length > kMaxFramePayload) {
            ++stats.format_errors;
            impl.rx_buffer.clear();
            disconnect_peer(impl);
            return;
        }
        const std::size_t total = kWireHeaderSize + payload_length;
        if (impl.rx_buffer.size() < total) {
            return;
        }
        std::vector<std::byte> frame(impl.rx_buffer.begin(),
                                     impl.rx_buffer.begin() +
                                         static_cast<std::ptrdiff_t>(total));
        impl.rx_buffer.erase(
            impl.rx_buffer.begin(),
            impl.rx_buffer.begin() + static_cast<std::ptrdiff_t>(total));
        if (impl.newest) {
            ++stats.dropped_stale;
        }
        impl.newest = std::move(frame);
    }
}

}  // namespace

bool TcpTransport::send(ByteSpan frame) {
    if (impl_->listener == detail::kInvalidSocket && impl_->peer == detail::kInvalidSocket) {
        throw TransportError("tcp transport: send before initialize()");
    }
    if (!ensure_connected(*impl_)) {
        return false;
    }
    flush_send_queue(*impl_, stats_);
    if (impl_->queued_bytes + frame.size() > kMaxQueuedBytes) {
        return false;
    }
    impl_->send_queue.emplace_back(frame.begin(), frame.end());
    impl_->queued_bytes += frame.size();
    flush_send_queue(*impl_, stats_);
    return true;
}

std::optional<std::vector<std::byte>> TcpTransport::receive() {
    if (impl_->listener == detail::kInvalidSocket && impl_->peer == detail::kInvalidSocket) {
        throw TransportError("tcp transport: receive before initialize()");
    }
    if (!ensure_connected(*impl_)) {
        return std::nullopt;
    }
    flush_send_queue(*impl_, stats_);

    for (;;) {
        const ssize_t count = ::recv(impl_->peer, impl_->receive_buffer.data(),
                                     impl_->receive_buffer.size(), 0);
        if (count < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break;
            }
            disconnect_peer(*impl_);
            break;
        }
        if (count == 0) {
            disconnect_peer(*impl_);
            break;
        }
        impl_->rx_buffer.insert(
            impl_->rx_buffer.end(), impl_->receive_buffer.begin(),
            impl_->receive_buffer.begin() + static_cast<std::ptrdiff_t>(count));
        extract_frames(*impl_, stats_);
        if (impl_->peer == detail::kInvalidSocket) {
            break;
        }
    }

    if (!impl_->newest) {
        return std::nullopt;
    }
    std::vector<std::byte> frame = std::move(*impl_->newest);
    impl_->newest.reset();
    ++stats_.frames_received;
    return frame;
}

namespace {
const bool kTcpRegistered = register_transport(
    "tcp", []() -> std::unique_ptr<Transport> {
        return std::make_unique<TcpTransport>();
    });
}

}  // namespace transport
}  // namespace pyfmi_interop

#endif  // _WIN32
