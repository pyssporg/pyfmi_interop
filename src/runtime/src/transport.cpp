#include "pyfmi_interop/runtime/transport.hpp"

#include <algorithm>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace pyfmi_interop {
namespace {

using Registry = std::map<std::string, TransportFactory, std::less<>>;

Registry& registry() {
    static Registry instance;
    return instance;
}

std::mutex& registry_mutex() {
    static std::mutex instance;
    return instance;
}

// A bare name (`loopback`) and a full URI (`udp://host:port?peer=...`) both
// select by their scheme; everything after "://" configures the backend in
// initialize().
std::string scheme_of(const std::string& name_or_uri) {
    const std::size_t separator = name_or_uri.find("://");
    return separator == std::string::npos ? name_or_uri
                                          : name_or_uri.substr(0, separator);
}

}  // namespace

bool register_transport(const std::string& name, TransportFactory factory) {
    if (name.empty() || factory == nullptr) {
        return false;
    }
    std::lock_guard<std::mutex> lock(registry_mutex());
    registry()[name] = factory;
    return true;
}

std::unique_ptr<Transport> make_transport(const std::string& name_or_uri) {
    const std::string scheme = scheme_of(name_or_uri);

    TransportFactory factory = nullptr;
    {
        std::lock_guard<std::mutex> lock(registry_mutex());
        const auto found = registry().find(scheme);
        if (found != registry().end()) {
            factory = found->second;
        }
    }

    if (factory == nullptr) {
        std::string known;
        for (const std::string& name : transport_names()) {
            if (!known.empty()) {
                known += ", ";
            }
            known += name;
        }
        throw TransportError("unknown transport '" + scheme +
                             "'; known transports: " + known);
    }
    return factory();
}

std::vector<std::string> transport_names() {
    std::vector<std::string> names;
    {
        std::lock_guard<std::mutex> lock(registry_mutex());
        names.reserve(registry().size());
        for (const auto& entry : registry()) {
            names.push_back(entry.first);
        }
    }
    std::sort(names.begin(), names.end());
    return names;
}

}  // namespace pyfmi_interop
