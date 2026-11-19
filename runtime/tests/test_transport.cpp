#include "pyfmi_interop/runtime/loopback_transport.hpp"
#include "pyfmi_interop/runtime/transport.hpp"
#include "pyfmi_interop/runtime/wire.hpp"
#include "pyfmi_interop/transport/tcp_transport.hpp"
#include "pyfmi_interop/transport/udp_transport.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
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
    const auto model_id = pyfmi_interop::wire::model_id("transport-test", 0.01, {});
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

}  // namespace

int main() {
    // Registry: names sorted, unknown name lists every backend.
    const std::vector<std::string> names = pyfmi_interop::transport_names();
    if (!std::is_sorted(names.begin(), names.end()) ||
        std::find(names.begin(), names.end(), "loopback") == names.end() ||
        std::find(names.begin(), names.end(), "udp") == names.end() ||
        std::find(names.begin(), names.end(), "tcp") == names.end()) {
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

    return EXIT_SUCCESS;
}
