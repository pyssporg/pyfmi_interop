# Architecture

`pyfmi_interop` is split into a Python generation layer, a reusable C++
runtime, and the generated model that joins them. The generator and the runtime
meet at one interface: `ModelRuntime`. Everything above it is generated; nothing
below it knows the model's signals or equations.

## Layers

### Python generation layer

| Module | Responsibility |
| --- | --- |
| `src/pyfmi_interop/ir.py` | `ModelDefinition`, `Signal`, `RateGroup`, value-reference assignment, canonical JSON. |
| `src/pyfmi_interop/sysml.py` | Ingestion through `pycps_sysml2` and `pyfmi_sysml2` into the IR. |
| `src/pyfmi_interop/timing.py` | Rate and deadline validation, step alignment, and schedule construction. |
| `src/pyfmi_interop/codegen/` | Emits the C++ source tree and the per-model `CMakeLists.txt`. |
| `src/pyfmi_interop/builder.py` | Configures and runs the CMake build. |
| `src/pyfmi_interop/packaging.py` | Emits FMI 2.0 `modelDescription.xml` and the deterministic `.fmu` zip. |
| `src/pyfmi_interop/cli.py` | The `pyfmi-interop` command surface. |

### C++ runtime layer

`runtime/` is a static runtime shared by every generated model:

- `ModelRuntime` — the interface between a generated model and the FMI facade,
  the scheduler, and the transports.
- The fixed-step realtime scheduler — owns the clock, the step loop, deadline
  accounting, and the optional spin-wait.
- `Transport` — the byte-frame exchange interface and registry. The in-process
  loopback backend is always built; protocol bindings are not part of this
  repository.

### Wire layer

`src/pyfmi_interop/wire/` and `runtime/src/wire.cpp` implement the same
length-delimited, CRC32-checked, version-tagged envelope. `schema.py` emits the
protobuf payload schema and its `wire.json` descriptor. Byte transports carry
the frame; discovery, medium, and protocol semantics are outside this
repository.

### Generated model layer

Per model, codegen emits a small C++17 project (`model_runtime.hpp`,
`model_runtime.cpp`, `model_impl.hpp`, `bindings.cpp`, `model.json`, and
`CMakeLists.txt`) with:

- typed signal members and value-reference accessors;
- publish and consume hooks that carry the step frame;
- the `user_step` hook, where the model's equations belong;
- the global factory `pyfmi_interop_create_model` and its destroy function.

### Wheel layer

The platform wheel (tag `py3-none-<platform>`) carries
`_runtime/libpyfmi_interop_runtime.a` plus the public headers under
`_runtime/include/pyfmi_interop/runtime/`. The wheel is not pure Python:
the native runtime must be built with CMake before `python -m build`.

## Data flow

```text
SysML v2 (.sysml) ──┐
                    ├─► sysml.py ─► ModelDefinition IR ─► codegen/ ─► C++ + CMakeLists.txt
IR JSON (model.json)┘                                      │
                                                           ▼
                                              builder.py ─► CMake ─► model library
                                                           │
                                                           ▼
                                              packaging.py ─► modelDescription.xml + .fmu
```

The IR is the only hand-off between ingestion, codegen, and packaging. Each
downstream stage reads the same signal order and value references, so the
generated header, the runtime accessors, and the FMI variables cannot disagree.

## Realtime design

- **Fixed step.** The scheduler advances by the model's `step_size_s`. Rate
  groups must be integer multiples of that step; `timing.py` validates the plan
  before generation.
- **Preallocated frames.** Signal storage and the `Sample` frames exchanged with
  transports are sized once during initialization. The scheduler reuses the
  same frame every step.
- **No allocation in the step path.** Numeric values are trivially copyable.
  String signals carry a fixed capacity, so the fast path performs no heap
  traffic. A transport backend allocates queues and serialization buffers in
  `initialize()`, never in `send` or `receive`.
- **Deadline and overrun accounting.** Every step has a deadline. The scheduler
  measures completion time, records overruns, and applies the configured policy:
  `Warn` keeps the original schedule, `Skip` re-anchors the next deadline, and
  `Fail` stops the run with an error. An overrun is visible; it is not silently
  absorbed.
- **Optional spin-wait.** A build or runtime option can spin-wait to reduce
  wake-up latency at the cost of CPU. It is not the default.
- **Threads.** The standalone scheduler runs its step loop on the realtime
  thread. The FMI facade is synchronous: `fmi2DoStep` calls
  `ModelRuntime::step` on the caller's thread and creates no background
  thread.

## Transport boundary

The repository defines the wire frame, not a protocol. Byte transports
(`udp`, `tcp`, `unix`) carry the frame; this tree ships the `Transport`
interface, the always-built in-process loopback backend, and no protocol
binding. A backend reports availability from `available()`; an unknown name or
unavailable backend surfaces an error rather than substituting another
transport.

## Generated versus runtime boundary

| Owned by the generator | Owned by the runtime | Owned by the user |
| --- | --- | --- |
| signal members and accessors | `ModelRuntime`, scheduler, `Transport` registry | `user_step` equations |
| publish/consume hooks | loopback frames and transport lifecycle | transport configuration values |
| factory and CMakeLists | FMI facade and deadline accounting | model parameters and initial values |
| FMI XML and archive | static runtime and headers | — |

Generated sources are build output, with one exception: `model_impl.hpp` holds
the `user_step` hook and is the only generated file meant to be edited. Change
the IR, a generator module, or a template for everything else, then regenerate;
a hand edit to any other generated file is lost on the next build and hides the
real source of the change.
