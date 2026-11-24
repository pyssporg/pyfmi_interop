#include "pyfmi_interop/transport/transport_uri.hpp"

#include <cctype>
#include <cstddef>
#include <limits>
#include <string>
#include <string_view>

#if !defined(_WIN32)
#include <sys/un.h>
#endif

namespace pyfmi_interop {
namespace transport {
namespace {

// A pathname needs its trailing NUL and an abstract name needs its leading NUL
// inside sun_path.  Win32 has no AF_UNIX in this tree yet; keep the Linux
// capacity there so the parser stays compilable and the diagnostics stable.
#if defined(_WIN32)
constexpr std::size_t kUnixPathCapacity = 108;
#else
constexpr std::size_t kUnixPathCapacity = sizeof(sockaddr_un::sun_path);
#endif

std::string trim(std::string_view text) {
    std::size_t begin = 0;
    std::size_t end = text.size();
    while (begin < end && std::isspace(static_cast<unsigned char>(text[begin])) != 0) {
        ++begin;
    }
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1])) != 0) {
        --end;
    }
    return std::string(text.substr(begin, end - begin));
}

std::uint16_t parse_port(const std::string& text) {
    if (text.empty()) {
        throw TransportError("transport URI: missing port");
    }
    unsigned long value = 0;
    for (const char character : text) {
        if (std::isdigit(static_cast<unsigned char>(character)) == 0) {
            throw TransportError("transport URI: port '" + text +
                                 "' is not a decimal number");
        }
        value = value * 10u + static_cast<unsigned long>(character - '0');
        if (value > std::numeric_limits<std::uint16_t>::max()) {
            throw TransportError("transport URI: port '" + text + "' is out of range");
        }
    }
    return static_cast<std::uint16_t>(value);
}

Endpoint parse_endpoint(const std::string& text, const char* field) {
    if (text.empty()) {
        throw TransportError(std::string("transport URI: empty ") + field);
    }

    Endpoint endpoint;
    std::string port_text;
    if (text.front() == '[') {
        const std::size_t close = text.find(']');
        if (close == std::string::npos) {
            throw TransportError(std::string("transport URI: unterminated IPv6 ") + field);
        }
        endpoint.host = text.substr(1, close - 1);
        if (close + 1 >= text.size() || text[close + 1] != ':') {
            throw TransportError(std::string("transport URI: missing port in ") + field);
        }
        port_text = text.substr(close + 2);
    } else {
        const std::size_t colon = text.rfind(':');
        if (colon == std::string::npos) {
            throw TransportError(std::string("transport URI: missing ':port' in ") + field);
        }
        endpoint.host = text.substr(0, colon);
        port_text = text.substr(colon + 1);
    }
    endpoint.port = parse_port(port_text);
    if (endpoint.host.empty()) {
        endpoint.host = "0.0.0.0";
    }
    return endpoint;
}

std::string parse_unix_path(const std::string& text, const char* field) {
    if (text.empty()) {
        throw TransportError(std::string("transport URI: empty unix ") + field);
    }
    if (text.find('\0') != std::string::npos) {
        throw TransportError(std::string("transport URI: unix ") + field +
                             " contains a NUL byte");
    }
    if (text.front() == '@') {
        if (text.size() == 1u) {
            throw TransportError(std::string("transport URI: abstract unix ") + field +
                                 " has an empty name");
        }
        // One leading NUL plus the name must fit in sun_path.
        if (text.size() >= kUnixPathCapacity) {
            throw TransportError(std::string("transport URI: unix ") + field + " '" +
                                 text + "' exceeds the " +
                                 std::to_string(kUnixPathCapacity - 1u) +
                                 "-byte sun_path limit");
        }
        return text;
    }
    if (text.front() != '/') {
        throw TransportError(std::string("transport URI: unix ") + field + " '" + text +
                             "' must be an absolute path or an '@name'");
    }
    // The pathname and its trailing NUL must fit in sun_path.
    if (text.size() >= kUnixPathCapacity) {
        throw TransportError(std::string("transport URI: unix ") + field + " '" + text +
                             "' exceeds the " +
                             std::to_string(kUnixPathCapacity - 1u) +
                             "-byte sun_path limit");
    }
    return text;
}

}  // namespace

std::string scheme_of(std::string_view name_or_uri) {
    const std::size_t separator = name_or_uri.find("://");
    return std::string(separator == std::string_view::npos
                           ? name_or_uri
                           : name_or_uri.substr(0, separator));
}

Uri parse_uri(std::string_view uri) {
    const std::string text = trim(uri);
    if (text.empty()) {
        throw TransportError("transport URI is empty");
    }

    Uri parsed;
    const std::size_t separator = text.find("://");
    if (separator == std::string::npos) {
        parsed.scheme = text;
        parsed.bind.host = "0.0.0.0";
        parsed.bind.port = 0;
        return parsed;
    }

    parsed.scheme = text.substr(0, separator);
    if (parsed.scheme.empty()) {
        throw TransportError("transport URI: missing scheme before '://'");
    }

    std::string rest = text.substr(separator + 3);
    std::string query;
    const std::size_t question = rest.find('?');
    if (question != std::string::npos) {
        query = rest.substr(question + 1);
        rest = rest.substr(0, question);
    }
    if (parsed.scheme == "unix") {
        parsed.bind_path = parse_unix_path(rest, "bind address");
    } else {
        parsed.bind = parse_endpoint(rest, "bind endpoint");
    }

    if (!query.empty()) {
        std::size_t offset = 0;
        while (offset <= query.size()) {
            const std::size_t ampersand = query.find('&', offset);
            const std::string option =
                query.substr(offset, ampersand == std::string::npos
                                         ? std::string::npos
                                         : ampersand - offset);
            if (!option.empty()) {
                const std::size_t equals = option.find('=');
                if (equals == std::string::npos) {
                    throw TransportError("transport URI: option '" + option +
                                         "' is not key=value");
                }
                const std::string key = option.substr(0, equals);
                const std::string value = option.substr(equals + 1);
                if (key == "peer") {
                    if (parsed.scheme == "unix") {
                        parsed.peer_path = parse_unix_path(value, "peer address");
                    } else {
                        parsed.peer = parse_endpoint(value, "peer endpoint");
                    }
                } else {
                    throw TransportError("transport URI: unknown option '" + key + "'");
                }
            }
            if (ampersand == std::string::npos) {
                break;
            }
            offset = ampersand + 1;
        }
    }

    return parsed;
}

}  // namespace transport
}  // namespace pyfmi_interop
