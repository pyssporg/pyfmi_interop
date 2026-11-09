#include "pyfmi_distributed/runtime/model_runtime.hpp"

#include <algorithm>
#include <utility>

namespace pyfmi_distributed {

Value Value::make_real(double value) {
    Value result;
    result.type = DataType::Real;
    result.real_value = value;
    return result;
}

Value Value::make_integer(std::int32_t value) {
    Value result;
    result.type = DataType::Integer;
    result.integer_value = value;
    return result;
}

Value Value::make_boolean(bool value) {
    Value result;
    result.type = DataType::Boolean;
    result.boolean_value = value;
    return result;
}

Value Value::make_string(const char* value) {
    Value result;
    result.type = DataType::String;
    if (value != nullptr) {
        result.string_value = value;
    }
    return result;
}

void Value::assign_from(const Value& other) {
    real_value = other.real_value;
    integer_value = other.integer_value;
    boolean_value = other.boolean_value;
    // String assignment may allocate when the destination capacity is too
    // small.  Frames are reused across steps, so in steady state assignment
    // reuses the existing buffer; string signals are documented as a
    // recovery-path feature and are excluded from the deadline-critical path.
    string_value = other.string_value;
}

void Sample::resize(std::size_t signal_count) {
    values.resize(signal_count);
    valid.assign(signal_count, static_cast<unsigned char>(0));
}

bool Sample::is_valid(std::uint32_t value_reference) const {
    return static_cast<std::size_t>(value_reference) < valid.size() &&
           valid[value_reference] != 0;
}

void Sample::clear_valid() {
    std::fill(valid.begin(), valid.end(), static_cast<unsigned char>(0));
}

}  // namespace pyfmi_distributed
