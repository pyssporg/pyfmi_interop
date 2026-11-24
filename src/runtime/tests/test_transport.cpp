#include "pyfmi_interop/runtime/loopback_transport.hpp"
#include "pyfmi_interop/runtime/transport.hpp"
#include "pyfmi_interop/runtime/wire.hpp"
#include "pyfmi_interop/transport/tcp_transport.hpp"
#include "pyfmi_interop/transport/udp_transport.hpp"
#include "pyfmi_interop/transport/unix_transport.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace {

using pyfmi_interop::LoopbackTransport;
using pyfmi_interop::Transport;
using pyfmi_interop::TransportError;
using pyfmi_interop::TransportStats;
using pyfmi_interop::transport::TcpTransport;
using pyfmi_interop::transport::UdpTransport;
using pyfmi_interop::transport::UnixTransport;

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

std::vector<std::byte> to_bytes(const std::vector<std::uint8_t>& bytes) {
    std::vector<std::byte> converted(bytes.size());
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        converted[index] = static_cast<std::byte>(bytes[index]);
    }
    return converted;
}

bool equals(const std::optional<std::vector<std::byte>>& frame,
            const std::vector<std::uint8_t>& expected) {
    return frame.has_value() && frame->size() == expected.size() &&
           std::equal(frame->begin(), frame->end(), expected.begin(),
                      [](std::byte left, std::uint8_t right) {
                          return std::to_integer<std::uint8_t>(left) == right;
                      });
}

std::vector<std::uint8_t> sample_frame() {
    const auto model_id = pyfmi_interop::wire::model_id("transport-test", {});
    const auto encoded = pyfmi_interop::wire::encode_frame(
        model_id, "hello", 1, 1, 0, pyfmi_interop::wire::PayloadFormat::Opaque);
    return encoded.frame;
}

bool send_all(int socket, const std::uint8_t* data, std::size_t size) {
    std::size_t offset = 0;
    while (offset < size) {
        const ssize_t written = ::send(socket, data + offset, size - offset, 0);
        if (written <= 0) {
            return false;
        }
        offset += static_cast<std::size_t>(written);
    }
    return true;
}

int raw_connect(std::uint16_t port) {
    const int socket = ::socket(AF_INET, SOCK_STREAM, 0);
    if (socket < 0) {
        return -1;
    }
    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(socket, reinterpret_cast<const sockaddr*>(&address),
                  sizeof(address)) != 0) {
        ::close(socket);
        return -1;
    }
    return socket;
}

std::string unique_socket_path(const char* tag) {
    return "/tmp/pyfmi_interop_unix_" + std::to_string(::getpid()) + "_" + tag +
           ".sock";
}

socklen_t unix_address_length(const std::string& path) {
    return static_cast<socklen_t>(offsetof(sockaddr_un, sun_path) + path.size() + 1u);
}

bool bind_raw_datagram(const std::string& path) {
    const int socket = ::socket(AF_UNIX, SOCK_DGRAM, 0);
    if (socket < 0) {
        return false;
    }
    sockaddr_un address {};
    address.sun_family = AF_UNIX;
    std::memcpy(address.sun_path, path.c_str(), path.size() + 1u);
    const bool bound =
        ::bind(socket, reinterpret_cast<const sockaddr*>(&address),
               unix_address_length(path)) == 0;
    ::close(socket);
    return bound;
}

std::optional<std::vector<std::byte>> receive_retry(Transport& transport) {
    std::optional<std::vector<std::byte>> frame;
    for (int attempt = 0; attempt < 2000 && !frame; ++attempt) {
        frame = transport.receive();
        if (!frame) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    return frame;
}

}  // namespace

int main() {
    // Registry: names sorted, unknown name lists every backend.
    const std::vector<std::string> names = pyfmi_interop::transport_names();
    if (!std::is_sorted(names.begin(), names.end()) ||
        std::find(names.begin(), names.end(), "loopback") == names.end() ||
        std::find(names.begin(), names.end(), "udp") == names.end() ||
        std::find(names.begin(), names.end(), "tcp") == names.end() ||
        std::find(names.begin(), names.end(), "unix") == names.end()) {
        return fail("transport registry names");
    }
    try {
        (void)pyfmi_interop::make_transport("does-not-exist");
        return fail("unknown transport must throw");
    } catch (const TransportError& error) {
        const std::string message = error.what();
        if (message.find("known transports:") == std::string::npos ||
            message.find("loopback") == std::string::npos) {
            return fail("unknown transport message must list known names");
        }
    }

    const std::vector<std::uint8_t> expected = sample_frame();

    // Loopback byte round trip and stale drop.  Constructing the class
    // directly also keeps its registration object linked in this test binary.
    {
        LoopbackTransport loopback;
        std::vector<std::byte> first(expected.size(), std::byte{0x01});
        std::vector<std::byte> second = to_bytes(expected);
        if (!loopback.send(first) || !loopback.send(second)) {
            return fail("loopback send");
        }
        const auto received = loopback.receive();
        if (!equals(received, expected)) {
            return fail("loopback round trip");
        }
        const TransportStats stats = loopback.stats();
        if (stats.frames_sent != 2 || stats.frames_received != 1 ||
            stats.dropped_stale != 1) {
            return fail("loopback stats");
        }
    }

    // UDP round trip over 127.0.0.1 with an ephemeral receive port.
    {
        UdpTransport receiver;
        receiver.initialize("udp://127.0.0.1:0");
        UdpTransport sender;
        sender.initialize("udp://127.0.0.1:0?peer=127.0.0.1:" +
                          std::to_string(receiver.bound_port()));
        if (!sender.send(to_bytes(expected))) {
            return fail("udp send");
        }
        std::optional<std::vector<std::byte>> received;
        for (int attempt = 0; attempt < 2000 && !received; ++attempt) {
            received = receiver.receive();
            if (!received) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
        if (!equals(received, expected)) {
            return fail("udp round trip");
        }
        if (sender.stats().frames_sent != 1 || receiver.stats().frames_received != 1) {
            return fail("udp stats");
        }

        std::vector<std::byte> oversized(65508, std::byte{0});
        try {
            (void)sender.send(oversized);
            return fail("udp must reject a frame larger than 65507 bytes");
        } catch (const TransportError&) {
        }
    }

    // TCP reassembly: header and payload arrive in separate writes.
    {
        TcpTransport server;
        server.initialize("tcp://127.0.0.1:0");
        const int client = raw_connect(server.bound_port());
        if (client < 0) {
            return fail("tcp raw connect");
        }

        const std::size_t header_size = pyfmi_interop::wire::kHeaderSize;
        if (!send_all(client, expected.data(), header_size)) {
            ::close(client);
            return fail("tcp split header write");
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        if (!send_all(client, expected.data() + header_size,
                      expected.size() - header_size)) {
            ::close(client);
            return fail("tcp split payload write");
        }

        std::optional<std::vector<std::byte>> received;
        for (int attempt = 0; attempt < 2000 && !received; ++attempt) {
            received = server.receive();
            if (!received) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
        if (!equals(received, expected)) {
            ::close(client);
            return fail("tcp split-frame reassembly");
        }
        if (server.stats().frames_received != 1) {
            ::close(client);
            return fail("tcp stats");
        }

        // Server -> client send path.
        if (!server.send(to_bytes(expected))) {
            ::close(client);
            return fail("tcp send");
        }
        std::vector<std::uint8_t> received_bytes(expected.size());
        std::size_t offset = 0;
        while (offset < received_bytes.size()) {
            const ssize_t count = ::recv(client, received_bytes.data() + offset,
                                         received_bytes.size() - offset, 0);
            if (count <= 0) {
                break;
            }
            offset += static_cast<std::size_t>(count);
        }
        ::close(client);
        if (offset != expected.size() || received_bytes != expected) {
            return fail("tcp send payload");
        }
    }

    // Unix pathname round trip.  The receiver replies to the last observed
    // sender because it has no peer=, so both directions are covered.
    {
        const std::string receiver_path = unique_socket_path("rx");
        const std::string sender_path = unique_socket_path("tx");
        (void)::unlink(receiver_path.c_str());
        (void)::unlink(sender_path.c_str());

        UnixTransport receiver;
        receiver.initialize("unix://" + receiver_path);
        UnixTransport sender;
        sender.initialize("unix://" + sender_path + "?peer=" + receiver_path);
        if (receiver.bound_path() != receiver_path ||
            sender.bound_path() != sender_path) {
            return fail("unix bound_path");
        }
        if (!sender.send(to_bytes(expected))) {
            return fail("unix pathname send");
        }
        const auto received = receive_retry(receiver);
        if (!equals(received, expected)) {
            return fail("unix pathname round trip");
        }
        if (sender.stats().frames_sent != 1 || receiver.stats().frames_received != 1) {
            return fail("unix pathname stats");
        }
        if (!receiver.send(to_bytes(expected))) {
            return fail("unix reply to last sender send");
        }
        const auto reply = receive_retry(sender);
        if (!equals(reply, expected)) {
            return fail("unix reply to last sender");
        }
    }

    // Abstract-namespace round trip: no filesystem entry and no cleanup.
    {
        const std::string receiver_name =
            "@pyfmi_interop_abs_rx_" + std::to_string(::getpid());
        const std::string sender_name =
            "@pyfmi_interop_abs_tx_" + std::to_string(::getpid());
        UnixTransport receiver;
        receiver.initialize("unix://" + receiver_name);
        UnixTransport sender;
        sender.initialize("unix://" + sender_name + "?peer=" + receiver_name);
        if (!sender.send(to_bytes(expected))) {
            return fail("unix abstract send");
        }
        const auto received = receive_retry(receiver);
        if (!equals(received, expected)) {
            return fail("unix abstract round trip");
        }
    }

    // A pathname left behind by a closed socket is stale; initialize unlinks
    // it before bind.  finalize removes the pathname this instance created.
    {
        const std::string path = unique_socket_path("stale");
        (void)::unlink(path.c_str());
        if (!bind_raw_datagram(path)) {
            return fail("unix raw stale bind");
        }
        UnixTransport transport;
        transport.initialize("unix://" + path);
        if (transport.bound_path() != path) {
            return fail("unix stale rebind");
        }
        transport.finalize();
        if (::access(path.c_str(), F_OK) == 0) {
            return fail("unix finalize must remove its pathname");
        }
        transport.initialize("unix://" + path);
        transport.finalize();
    }

    // Oversize frames map to TransportError before any send.
    {
        const std::string path = unique_socket_path("oversize");
        UnixTransport transport;
        transport.initialize("unix://" + path);
        std::vector<std::byte> oversized(65508, std::byte{0});
        try {
            (void)transport.send(oversized);
            return fail("unix must reject a frame larger than 65507 bytes");
        } catch (const TransportError&) {
        }
    }

    return EXIT_SUCCESS;
}
