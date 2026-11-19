#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace pyfmi_interop {

// FMI scalar types supported by the realtime runtime.
enum class DataType { Real, Integer, Boolean, String };

enum class Direction { Input, Output, Parameter };

// One typed value.  Real, Integer and Boolean are trivially copyable and never
// allocate.  String carries storage because the FMI ABI hands out C strings;
// string signals are a recovery-path feature and are excluded from the
// deadline-critical fast path by the scheduler.
struct Value {
    DataType type = DataType::Real;
    double real_value = 0.0;
    std::int32_t integer_value = 0;
    bool boolean_value = false;
    std::string string_value;

    static Value make_real(double value);
    static Value make_integer(std::int32_t value);
    static Value make_boolean(bool value);
    static Value make_string(const char* value);

    // Copies the payload of `other`, leaving `type` untouched.  The scheduler
    // uses this on preallocated frames so no allocation happens per step.
    void assign_from(const Value& other);
};

// Preallocated frame exchanged with a transport.  `values` and `valid` are
// sized once from the model's value-reference count; the scheduler reuses the
// same frame every step.
struct Sample {
    double simulation_time = 0.0;
    std::vector<Value> values;
    std::vector<unsigned char> valid;

    void resize(std::size_t signal_count);
    bool is_valid(std::uint32_t value_reference) const;
    void clear_valid();
};

// Interface contract between the generated model and the reusable runtime.
// A generated model implements this class; the FMI facade, scheduler and
// transport layer only ever see this interface.
struct SignalDescriptor {
    std::string name;
    std::uint32_t value_reference = 0;
    DataType type = DataType::Real;
    Direction direction = Direction::Input;
    // 0.0 means "every scheduler step"; otherwise the signal is exchanged at
    // this period.  It must be an integer multiple of the model step size.
    double period = 0.0;
    // Fixed capacity for string signals (0 for numeric types).
    std::uint32_t capacity = 0;
};

class ModelRuntime {
public:
    virtual ~ModelRuntime() = default;

    virtual const std::vector<SignalDescriptor>& signals() const = 0;

    // Clears outputs and restores initial values.  Propagation of parameters
    // into the model state is performed by the generated implementation.
    virtual void reset() = 0;

    // Advances the model by `step_size` seconds.  Called only from the realtime
    // thread.  Implementations must not block and must not allocate.
    virtual void step(double time, double step_size) = 0;

    // Value-reference access.  Return false for unknown value references or a
    // direction mismatch; the FMI facade maps that to fmi2Error.
    virtual bool read(std::uint32_t value_reference, Value& out) const = 0;
    virtual bool write(std::uint32_t value_reference, const Value& value) = 0;

    // Transport exchange hooks.  The generated model owns sample population;
    // defaults are no-ops.  Both hooks run inside the step deadline and must
    // not allocate.
    virtual void publish(Sample& sample) const { (void)sample; }
    virtual void consume(const Sample& sample) { (void)sample; }
};

}  // namespace pyfmi_interop

// Factory supplied by the generated translation unit.  The default weak
// definition in the runtime returns nullptr, which makes the FMI facade report
// that the shared library was built without a model.  Declared at global scope
// because the symbols are looked up by the FMI importer through dlsym().
extern "C" pyfmi_interop::ModelRuntime* pyfmi_interop_create_model();
extern "C" void pyfmi_interop_destroy_model(pyfmi_interop::ModelRuntime* model);
