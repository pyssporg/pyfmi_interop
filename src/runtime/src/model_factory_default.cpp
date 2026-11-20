// Weak default model factory.  A generated model translation unit provides a
// strong definition of both symbols; linking it into the shared FMI facade
// then replaces these definitions.  Without a generated model the facade
// reports that the library contains no model.

#include "pyfmi_interop/runtime/model_runtime.hpp"

#if defined(__GNUC__) || defined(__clang__)
#define PYFMI_INTEROP_WEAK __attribute__((weak))
#elif defined(_MSC_VER)
// MSVC has no portable weak-function attribute.  The generated model must be
// compiled into the same target on that platform instead of replacing these.
#define PYFMI_INTEROP_WEAK
#else
#define PYFMI_INTEROP_WEAK
#endif

extern "C" PYFMI_INTEROP_WEAK pyfmi_interop::ModelRuntime*
pyfmi_interop_create_model() {
    return nullptr;
}

extern "C" PYFMI_INTEROP_WEAK void pyfmi_interop_destroy_model(
    pyfmi_interop::ModelRuntime* model) {
    delete model;
}
