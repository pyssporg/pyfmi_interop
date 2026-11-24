#include "pyfmi_interop/transport/unix_transport.hpp"

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
#error "pyfmi_interop unix transport: AF_UNIX is not implemented for Windows yet"
#else

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace pyfmi_interop {
namespace transport {
namespace {

constexpr std::size_t kMaxDatagram = 65507;
constexpr int kReceiveBufferBytes = 1 << 20;

sockaddr_un make_address(const std::string& value, socklen_t& length) {
    sockaddr_un address {};
    address.sun_family = AF_UNIX;

    if (value.empty()) {
        throw TransportError("unix transport: empty address");
    }
    if (value.front() == '@') {
        const std::string name = value.substr(1);
        if (name.empty()) {
            throw TransportError("unix transport: abstract name is empty");
        }
        // Leading NUL marks the abstract namespace; the name is not NUL
        // terminated and its length is carried by the sockaddr length.
        if (name.size() + 1u > sizeof(address.sun_path)) {
            throw TransportError("unix transport: abstract name '" + value +
                                 "' exceeds sun_path");
        }
        address.sun_path[0] = '\0';
        std::memcpy(address.sun_path + 1, name.data(), name.size());
        length = static_cast<socklen_t>(
            offsetof(sockaddr_un, sun_path) + 1u + name.size());
        return address;
    }

    if (value.front() != '/') {
        throw TransportError("unix transport: '" + value +
                             "' is not an absolute path or an '@name'");
    }
    if (value.size() + 1u > sizeof(address.sun_path)) {
        throw TransportError("unix transport: path '" + value +
                             "' exceeds sun_path");
    }
    std::memcpy(address.sun_path, value.c_str(), value.size() + 1u);
    length = static_cast<socklen_t>(
        offsetof(sockaddr_un, sun_path) + value.size() + 1u);
    return address;
}

// A pathname socket left behind by a crashed process is stale: bind may unlink
// it only when it is still a socket.  Anything else is refused, so binding
// never clobbers a regular file or directory.
void remove_stale_socket(const std::string& path) {
    struct stat info {};
    if (::lstat(path.c_str(), &info) != 0) {
        if (errno == ENOENT) {
            return;
        }
        throw TransportError("unix transport: cannot stat '" + path + "': " +
                             std::strerror(errno));
    }
    if (!S_ISSOCK(info.st_mode)) {
        throw TransportError("unix transport: refusing to unlink non-socket path '" +
                             path + "'");
    }
    if (::unlink(path.c_str()) != 0 && errno != ENOENT) {
        throw TransportError("unix transport: cannot unlink stale socket '" + path +
                             "': " + std::strerror(errno));
    }
}

void set_non_blocking(detail::socket_handle socket) {
    const int flags = ::fcntl(socket, F_GETFL, 0);
    if (flags < 0 || ::fcntl(socket, F_SETFL, flags | O_NONBLOCK) < 0) {
        throw TransportError("unix transport: cannot set O_NONBLOCK");
    }
}

}  // namespace

struct UnixTransport::Impl {
    detail::socket_handle socket = detail::kInvalidSocket;
    std::string bound_path;
    sockaddr_un peer {};
    socklen_t peer_length = 0;
    bool has_peer = false;
    sockaddr_un sender {};
    socklen_t sender_length = 0;
    bool has_sender = false;
    std::vector<std::byte> recv_buffer;
    std::optional<std::vector<std::byte>> newest;
};

UnixTransport::UnixTransport() : impl_(std::make_unique<Impl>()) {}

UnixTransport::~UnixTransport() {
    finalize();
}

void UnixTransport::initialize(const std::string& uri) {
    finalize();

    const Uri parsed = parse_uri(uri);
    if (parsed.scheme != "unix") {
        throw TransportError("unix transport: URI scheme is '" + parsed.scheme +
                             "', expected 'unix'");
    }
    if (parsed.bind_path.empty()) {
        throw TransportError(
            "unix transport: URI requires an address (unix:///path or unix://@name)");
    }

    impl_->socket = ::socket(AF_UNIX, SOCK_DGRAM, 0);
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("unix transport: socket() failed: " +
                             std::string(std::strerror(errno)));
    }

    int receive_buffer = kReceiveBufferBytes;
    (void)::setsockopt(impl_->socket, SOL_SOCKET, SO_RCVBUF, &receive_buffer,
                       sizeof(receive_buffer));

    socklen_t bind_length = 0;
    const sockaddr_un bind_address = make_address(parsed.bind_path, bind_length);
    const bool is_pathname = parsed.bind_path.front() != '@';
    if (is_pathname) {
        remove_stale_socket(parsed.bind_path);
    }
    if (::bind(impl_->socket, reinterpret_cast<const sockaddr*>(&bind_address),
               bind_length) != 0) {
        const std::string message = "unix transport: bind to '" + parsed.bind_path +
                                    "' failed: " + std::strerror(errno);
        finalize();
        throw TransportError(message);
    }
    impl_->bound_path = parsed.bind_path;
    set_non_blocking(impl_->socket);

    if (parsed.peer_path) {
        impl_->peer = make_address(*parsed.peer_path, impl_->peer_length);
        impl_->has_peer = true;
    }

    impl_->recv_buffer.resize(65536);
    impl_->newest.reset();
    impl_->has_sender = false;
    stats_ = {};
}

void UnixTransport::finalize() {
    if (impl_->socket != detail::kInvalidSocket) {
        (void)::close(impl_->socket);
        impl_->socket = detail::kInvalidSocket;
    }
    // A pathname we created belongs to this instance; abstract names live only
    // in the kernel namespace and need no cleanup.  Nothing here may throw.
    if (!impl_->bound_path.empty() && impl_->bound_path.front() != '@') {
        (void)::unlink(impl_->bound_path.c_str());
    }
    impl_->bound_path.clear();
    impl_->has_peer = false;
    impl_->has_sender = false;
    impl_->peer_length = 0;
    impl_->sender_length = 0;
    impl_->newest.reset();
}

bool UnixTransport::send(ByteSpan frame) {
    if (frame.size() > kMaxDatagram) {
        throw TransportError("unix transport: frame of " + std::to_string(frame.size()) +
                             " bytes exceeds the 65507-byte datagram limit");
    }
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("unix transport: send before initialize()");
    }

    const sockaddr_un* destination = nullptr;
    socklen_t destination_length = 0;
    if (impl_->has_peer) {
        destination = &impl_->peer;
        destination_length = impl_->peer_length;
    } else if (impl_->has_sender) {
        destination = &impl_->sender;
        destination_length = impl_->sender_length;
    } else {
        return false;  // No peer configured and no sender observed yet.
    }

    const ssize_t written = ::sendto(
        impl_->socket, frame.data(), frame.size(), 0,
        reinterpret_cast<const sockaddr*>(destination), destination_length);
    if (written < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == ENOBUFS) {
            return false;
        }
        if (errno == EMSGSIZE) {
            throw TransportError("unix transport: frame exceeds the datagram limit");
        }
        throw TransportError("unix transport: sendto failed: " +
                             std::string(std::strerror(errno)));
    }
    ++stats_.frames_sent;
    return true;
}

std::optional<std::vector<std::byte>> UnixTransport::receive() {
    if (impl_->socket == detail::kInvalidSocket) {
        throw TransportError("unix transport: receive before initialize()");
    }

    for (;;) {
        sockaddr_un from {};
        socklen_t from_length = sizeof(from);
        const ssize_t count = ::recvfrom(
            impl_->socket, impl_->recv_buffer.data(), impl_->recv_buffer.size(), 0,
            reinterpret_cast<sockaddr*>(&from), &from_length);
        if (count < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break;
            }
            throw TransportError("unix transport: recvfrom failed: " +
                                 std::string(std::strerror(errno)));
        }
        impl_->sender = from;
        impl_->sender_length = from_length;
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

std::string UnixTransport::bound_path() const {
    return impl_->bound_path;
}

REGISTER_TRANSPORT("unix", []() -> std::unique_ptr<Transport> {
    return std::make_unique<UnixTransport>();
});

}  // namespace transport
}  // namespace pyfmi_interop

#endif  // _WIN32
