# Architecture

`pyfmi_interop` is split into a Python generation layer, a reusable C++
runtime, and the generated model that joins them. The generator and the runtime
meet at one interface: `ModelRuntime`. Everything above it is generated; nothing
below it knows the model's signals or equations.

## Layers

### Python generation layer

The Python layer is split at the SysML boundary into `core/` (SysML-free) and
`sysml/` (ingestion and the adapter's FMI layer).

| Module | Responsibility |
| --- | --- |
| `src/pyfmi_interop/core/spec.py` | `ModelSpec` (the public interface contract) and `BuildConfig` (serialization, role, prefix). |
| `src/pyfmi_interop/core/ir.py` | `ModelDefinition`, `Signal`, `RateGroup`, value-reference assignment, canonical JSON. |
| `src/pyfmi_interop/core/timing.py` | Rate and deadline validation, step alignment, schedule construction. |
| `src/pyfmi_interop/core/codegen/` | Emits the C++ source tree and the per-model `CMakeLists.txt`. |
| `src/pyfmi_interop/core/builder.py` | Configures and runs the CMake build. |
| `src/pyfmi_interop/core/packaging.py` | Emits FMI 2.0 `modelDescription.xml` and the deterministic `.fmu` zip. |
| `src/pyfmi_interop/core/pipeline.py` | `Compilation` and `compile_model`: generate, build, package in one call. |
| `src/pyfmi_interop/sysml/parse.py` | One parse through `pycps_sysml2`, one reduction through `pyfmi_sysml2`; returns the parser-free `ParsedModel(spec, reduction, unit)`. |
| `src/pyfmi_interop/sysml/generate.py` | `generate_adapter(parsed, out_dir, config)`; never reloads the source. |
| `src/pyfmi_interop/sysml/adapter.py` | `adapter_from_reduction(reduction, model, ...)`: the `pyfmi_sysml2` FMI layer for the adapter artifact. |
| `src/pyfmi_interop/sysml/definitions/` | The bundled `PyfmiInterop` SysML vocabulary. |
| `src/pyfmi_interop/cli.py` | The `pyfmi-interop` command surface. |

`core/` imports no SysML package. The old import paths (`pyfmi_interop.ir`,
`.wire`, `.serialization`, `.codegen`, `.builder`, `.packaging`, `.schema`,
`.native`, `.roles`, `.timing`, `.psysml2`, `.definitions`) remain as
re-export-only compatibility facades.

A model may span packages: `load_model(includes=...)` and
`parse(..., includes=...)` (CLI: repeatable `--include PATH`) pass the same
extra roots to the single load. Export selection stays leaf-only among
`:> FmuModel` candidates, and imported definitions are selectable, so an app
file that only imports a library exports the library's leaf under its bare
name.

SysML is parsed exactly once: `parse` loads the architecture, reduces it once,
and returns the specification and the parser-free `Reduction` together;
`generate_adapter` consumes that `ParsedModel` rather than reloading the file
or re-resolving the export unit.

### C++ runtime layer

`src/runtime/` is a static runtime shared by every generated model:

- `ModelRuntime` — the interface between a generated model and the FMI facade,
  the scheduler, and the transports.
- The fixed-step realtime scheduler — owns the clock, the step loop, deadline
  accounting, and the optional spin-wait.
- `Transport` — the byte-frame exchange interface and registry. Loopback, UDP,
  and TCP are selected by name at run time; protocol bindings are not part of
  this repository.

### Wire layer

`src/pyfmi_interop/core/wire/` and `src/runtime/src/wire.cpp` implement the
same length-delimited, CRC32-checked, version-tagged envelope, the single
framing authority. Serialization is a registered seam with one schema authority
per backend: `core/serialization/protobuf.py` emits the canonical protobuf
payload schema, `core/serialization/descriptor.py` emits the shared `wire.json`,
and `packed` is the second backend; `core/schema.py` remains a
backwards-compatible facade. Wire version 2 carries `payload_format` in the
envelope, so one framing layer serves every backend.
Discovery, medium, and protocol semantics are outside this repository.

### Generated model layer

Per model, codegen emits a small C++17 project (`model_runtime.hpp`,
`model_runtime.cpp`, `model_impl.hpp`, `bindings.cpp`, `model.json`, and
`CMakeLists.txt`) with:

- typed signal members and value-reference accessors;
- publish and consume hooks that carry the step frame;
- the `user_step` hook, where the model's equations belong;
- the global factory `pyfmi_interop_create_model` and its destroy function.

The adapter variant emits the same interface publication and consumes the
corresponding wire direction, but carries no `user_step` and no equations.

Each artifact owns one FMI facade. The core emits the interop facade
(checked-in `src/runtime/src/fmi2_cs_api.cpp` plus
`core/packaging.render_model_description`); the adapter takes its FMI interface,
headers, and model description from `pyfmi_sysml2` and links the runtime
without whole-archive. Both export the same `fmi2*` ABI, so they never share a
binary.

### Wheel layer

The platform wheel (tag `py3-none-<platform>`) carries
`_runtime/libpyfmi_interop_runtime.a`, `_runtime/libpyfmi_interop_transport.a`,
the runtime and transport headers under `_runtime/include/`, and the shared
CMake module `_runtime/cmake/wire.cmake`. The wheel is not pure Python:
both native archives must be built with CMake before `python -m build`.

## Data flow

```text
SysML v2 (.sysml) ─► sysml/parse.py ─► ModelSpec ─┐
                                                  ├─► core/codegen/ ─► C++ + CMakeLists.txt
IR JSON (model.json) ─► ModelDefinition ──────────┘            │
                                                               ▼
                                                core/builder.py ─► CMake ─► model library
                                                               │
                                                               ▼
                                                core/packaging.py ─► modelDescription.xml + .fmu
```

`ModelSpec` projects onto the internal `ModelDefinition`, the only hand-off
between ingestion, codegen, and packaging. Each downstream stage reads the same
signal order and value references, so the generated header, the runtime
accessors, and the FMI variables cannot disagree.

## Adapter models and the wire path

The same part definition that yields the realtime model also yields an adapter
model. The adapter carries values on and off the byte transport; it has no
equations and no `user_step`. Its path has four layers:

```text
ModelDefinition IR ─► serializer ─► framing ─► transport
```

- **Serializer — compile-time lifetime.** The backend is chosen when the
  adapter is generated and compiled into it, one schema authority per backend:
  protobuf canonical, `packed` second, `opaque` for caller bytes. This is the
  dependency boundary.
- **Framing — one authority.** Every backend shares the length-delimited,
  CRC32-checked, version-tagged envelope; wire version 2 adds `payload_format`
  to it. Field numbers are append-only and the reserved range stays reserved.
- **Transport — run-time lifetime.** Loopback, UDP, and TCP are registered by
  name and resolved when the adapter runs. This is the deployment boundary:
  endpoints are instance parameters, never SSD/SSP content, so an SSP stays
  portable.

The deployment parameter port is initialization-only configuration: its members
are FMI `causality="parameter"`, `variability="fixed"`, writable before
`fmi2EnterInitializationMode`, and never wire fields. Runtime behaviour belongs
in `in` ports (FMI `causality="input"`), not parameters. `resources/transport.json`
lists `queue_depth` and `deadline_s` among the recognised keys, but the C++
runtime does not consume them; only `transport`, `bind_address`, and
`peer_address` select the transport.

One message carries the whole part definition: every input and output signal
field of every port, numbered `1..n` in the canonical signal-name order, with
parameters excluded. FMI value references are a separate namespace assigned by
the generated interface — zero-based, declaration order, parameters included —
so `wire.json` carries both and a parameter edit never renumbers the wire or
moves `model_id`. That order is stable when ports are reordered in SysML;
variable names, not value references, are what an SSP connector binds to.
Direction follows FMI causality:

| FMI causality | Adapter role | Wire direction |
| --- | --- | --- |
| `input` | publish | out |
| `output` | consume | in |
| `parameter` | none | never published |

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
(`loopback`, `udp`, `tcp`) carry the frame; this tree ships the `Transport`
interface and those registered backends, and no protocol binding. A transport
is selected at run time from the URI scheme by `make_transport()`; an unknown
scheme throws `TransportError` listing the registered names rather than
substituting another transport. Endpoints are deployment data resolved from
the instance's parameter interface (the environment is only a fallback) —
never SSD/SSP content, so a packaged SSP stays portable.

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
