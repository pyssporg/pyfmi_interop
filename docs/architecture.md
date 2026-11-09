# Architecture

`pyfmi_distributed` is split into a Python generation layer, a reusable C++
runtime, and the generated model that joins them. The generator and the runtime
meet at one interface: `ModelRuntime`. Everything above it is generated; nothing
below it knows the model's signals or equations.

## Layers

### Python generation layer

| Module | Responsibility |
| --- | --- |
| `src/pyfmi_distributed/ir.py` | `ModelDefinition`, `Signal`, `RateGroup`, `TransportBinding`, value-reference assignment, canonical JSON. |
| `src/pyfmi_distributed/sysml.py` | Ingestion through `pycps_sysml2` and `pyfmi_sysml2` into the IR. |
| `src/pyfmi_distributed/timing.py` | Rate and deadline validation, step alignment, and schedule construction. |
| `src/pyfmi_distributed/codegen/` | Emits the C++ source tree and the per-model `CMakeLists.txt`. |
| `src/pyfmi_distributed/builder.py` | Configures and runs the CMake build. |
| `src/pyfmi_distributed/packaging.py` | Emits FMI 2.0 `modelDescription.xml` and the deterministic `.fmu` zip. |
| `src/pyfmi_distributed/cli.py` | The `pyfmi-distributed` command surface. |

### C++ runtime layer

`runtime/` is a static runtime shared by every generated model:

- `ModelRuntime` — the interface between a generated model and the FMI facade,
  the scheduler, and the transports.
- The fixed-step realtime scheduler — owns the clock, the step loop, deadline
  accounting, and the optional spin-wait.
- `Transport` — the adapter interface and registry. The loopback adapter is
  always built. HLA, DIS, DCP, ROS 2, and ED-247 are compile-gated stubs behind
  `PYFMI_DIST_ENABLE_*`, default OFF. Protocol mapping code lives in
  `runtime/src/adapters/` and binds the prebuilt upstream library; the
  repository does not implement protocol serialization.

### Protocol dependency layer

`cmake/adapters.cmake` resolves the enabled adapter libraries, and `vcpkg.json`
declares the vcpkg features. The acquisition order is fixed:

1. an installed package discovered by `find_package()` (vcpkg or system);
2. a `third_party/<lib>` submodule checkout (`PYFMI_DIST_USE_SUBMODULES=ON`,
   default ON);
3. FetchContent of the pinned revision when `-DPYFMI_DIST_ALLOW_FETCH=ON`
   (default OFF);
4. a hard configuration error naming the upstream URL, pin, and instructions.

ROS 2 is system-only: source `/opt/ros/jazzy/setup.bash`, and never vendor
`rclcpp`. The dependency table and exact commands are in `docs/adapters.md`.

### Generated model layer

Per model, codegen emits a small C++17 project (`model_runtime.hpp`,
`model_runtime.cpp`, `model_impl.hpp`, `bindings.cpp`, `model.json`, and
`CMakeLists.txt`) with:

- typed signal members and value-reference accessors;
- publish and consume hooks for the bound transport channels;
- the `user_step` hook, where the model's equations belong;
- the global factory `pyfmi_distributed_create_model` and its destroy function.

### Wheel layer

The platform wheel (tag `py3-none-<platform>`) carries
`_runtime/libpyfmi_distributed_runtime.a` plus the public headers under
`_runtime/include/pyfmi_distributed/runtime/`. The wheel is not pure Python:
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
  traffic. Adapters allocate queues and serialization buffers in `initialize()`,
  never in `send` or `receive`.
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

## Adapter gating

`src/pyfmi_distributed/adapters.py` is the adapter catalogue. Each descriptor
names the adapter, its CMake option, its C++ class, its external requirement,
and its `AdapterDependency` metadata (acquisition, upstream, pin, license,
CMake package and targets, submodule path). The gate rules:

- an option OFF leaves a stub in the runtime; the package still links;
- `available()` returns false on a stub, and `initialize()` fails with an
  actionable error;
- an option ON without the library fails at CMake configuration or adapter
  initialization, with the missing dependency named;
- the library comes from an installed package, a `third_party/<lib>` submodule,
  or FetchContent with `-DPYFMI_DIST_ALLOW_FETCH=ON`, in that order;
- the repository never reimplements protocol serialization; mapping code lives
  in `runtime/src/adapters/`;
- DCP is ASAM X-DCP via DCPLib, not DDS;
- there is no silent fallback to loopback or to another transport.

## Generated versus runtime boundary

| Owned by the generator | Owned by the runtime | Owned by the user |
| --- | --- | --- |
| signal members and accessors | `ModelRuntime`, scheduler, `Transport` registry | `user_step` equations |
| binding publish/consume hooks | loopback frames and adapter lifecycle | adapter configuration values |
| factory and CMakeLists | FMI facade and deadline accounting | model parameters and initial values |
| FMI XML and archive | static runtime and headers | transport channel names in the IR |

Generated sources are build output, with one exception: `model_impl.hpp` holds
the `user_step` hook and is the only generated file meant to be edited. Change
the IR, a generator module, or a template for everything else, then regenerate;
a hand edit to any other generated file is lost on the next build and hides the
real source of the change.
