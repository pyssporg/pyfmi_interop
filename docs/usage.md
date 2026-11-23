# Usage

`pyfmi-interop` turns an interface specification — IR JSON or a `ModelSpec` —
into generated C++17 sources, builds them with CMake, and packages the result as
an FMI 2.0 CoSimulation FMU. It is SysML-free; SysML ingestion is the separate
`pyfmi-sysml` composition layer.

## Install

Build the native runtime before installing the Python package:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build

python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

A wheel install replaces the editable step with
`pip install pyfmi_interop-<version>-py3-none-<platform>.whl`. The wheel
carries the prebuilt static runtime and transport archives plus the public
headers and `wire.cmake`; it cannot be built without the native archives in
`build/runtime/`.

`pyfmi-interfaces` is a runtime dependency for the adapter FMI layer. There is
no `[sysml]` extra: SysML ingestion, its dialect packages, and the vocabulary
are installed with `pyfmi-sysml` from its own checkout.

## Inputs

`generate` accepts an IR JSON file through `--model-json`; that is the only CLI
input.

- **IR JSON** — the canonical `ModelDefinition` JSON, as written by
  `core/ir.py` and emitted as `<out>/model.json` next to every generated model.
  `model.json` is the internal build manifest, not a separate public schema; it
  carries the same fields the generator consumes, so it is the direct path for
  tests and for tools that build the IR themselves.
- **SysML v2** — ingested by `pyfmi_sysml`, which parses once, maps the
  parser-free reduction to a `ModelSpec`, and calls the interop generator. The
  CLI here has no `--sysml`, `--include`, or `--step-size`.

`examples/core/compile_model.py` drives the `ModelSpec` pipeline from Python.

`inspect` and `schema` take IR JSON only. Generate writes the IR to
`<out>/model.json`; inspect that file to validate the model and see the
resolved signal table:

```bash
pyfmi-interop inspect --model-json build/actuator_link/model.json
```

## Python API

The public core contract is `ModelSpec` (the interface) plus `BuildConfig`
(serialization, role, prefix). `compile_model` runs generate, build, and package
in one call; `generate_model`, `build_model`, and `package_fmu` are the stages:

```python
from pyfmi_interop.core import BuildConfig, ModelSpec, compile_model

spec = ModelSpec(name="demo", signals=(...), step_size_s=0.001)
result = compile_model(spec, "build/demo",
                       config=BuildConfig(serialization="packed"))
```

`generate_model(spec, out_dir, config)` emits the interop facade for the
realtime model. The adapter model and its `pyfmi_interfaces` facade live in
`pyfmi_interop.core.adapter`; a composition layer builds it from a parser-free
`Reduction`:

```python
from pyfmi_interop.core import BuildConfig, adapter_from_reduction

adapter = adapter_from_reduction(
    reduction,
    spec.to_model(BuildConfig(serialization="protobuf")),
    component=unit,
    serialization="protobuf",
)
```

`pyfmi_sysml` wraps that as `parse(source)` then
`generate_adapter(parsed, out_dir, config)`, never reloading the source or
re-resolving the export unit. Both artifacts export the same `fmi2*` ABI but
never share a binary.

## Generate

```bash
pyfmi-interop generate --model-json model.json --out build/model
pyfmi-interop build build/model --build-dir build/model-build
pyfmi-interop package build/model --library <library> --out demo.fmu
```

The CLI emits the realtime model. The adapter is a Python-API or
`pyfmi_sysml` workflow: the composition layer parses the source, selects the
export unit, and calls `generate_adapter`, which takes the adapter's facade from
`pyfmi_interfaces`.

Export selection is leaf-only among `:> FmuModel` candidates: a shared base such
as `FmuInterop :> FmuModel` is a role, not an FMU. Imported definitions are
selectable, so a library-defined leaf is the export unit and a direct FMU is
packaged under its bare name. `composition=`, `includes=`, `load_architecture`,
`fmu_units`, and the one-or-all-unit examples all live in `pyfmi_sysml`; see
its documentation.

Generation emits a small C++17 project: `model_runtime.hpp`,
`model_runtime.cpp`, `model_impl.hpp`, `bindings.cpp`, `model.json`, and
`CMakeLists.txt`, plus the artifacts of the selected serialization backend. The
source contains typed signal members, value-reference accessors,
publish/consume hooks, the `user_step` hook, and the
`pyfmi_interop_create_model` factory.

`--serialization` selects the payload backend (default `protobuf`):

| Backend | `format_id` | Artifacts |
| --- | ---: | --- |
| `protobuf` | 1 | `<Model>.proto`, `wire.json`, `model_wire.cpp`, `wire_conformance.cpp` |
| `packed` | 2 | `wire.json`, `model_wire.cpp`, `wire_conformance.cpp`; deterministic little-endian |
| `opaque` | 0 | `wire.json`; no schema and no codec, caller bytes pass through |

Run `pyfmi-interop serializations` to list the installed backends. The packed
layout, in value-reference order, is `float64` for real, `int32` for integer,
`uint8` (0/1) for boolean, and a `uint32` byte count followed by UTF-8 bytes for
string; there is no tag or padding.

The payload message is named after the part definition whose interface the
model carries (`demo_model` for a plain IR model), and each field identifier is
the interface name with `.`/`[` mapped to `_` (`out.value[0]` ->
`out_value_0`). Two names that map to the same identifier are an error, never a
silent rename. `wire.json` records the wire direction per field, which is the
inverse of FMI causality: an FMI input is wire `out`, an FMI output is wire
`in`, and parameters are `none`.

The interface role is derived from causality (`sender` inputs only, `receiver`
outputs only, `adapter` both, `none` neither) and written to `model.json` and
`wire.json`. `--role` may narrow it; a role that needs a causality the
interface does not carry is refused.

`model_impl.hpp` holds the empty `user_step` hook and is the one generated file
meant to be edited for model equations. Everything else is build output: change
the IR or a generator template and regenerate rather than hand-editing it.

## Build

```bash
pyfmi-interop build build/actuator_link
```

The build configures the per-model `CMakeLists.txt` in
`build/actuator_link/build/` and links the generated source against the static
runtime. The wire payload mode is selected the same way as the runtime build:

```bash
cmake -S build/actuator_link -B build/actuator_link/out \
  -DPYFMI_INTEROP_WIRE=protobuf \
  -DPYFMI_INTEROP_CMAKE_DIR=cmake \
  -DPYFMI_INTEROP_RUNTIME_INCLUDE_DIR=src/runtime/include \
  -DPYFMI_INTEROP_RUNTIME_LIBRARY=build/runtime/libpyfmi_interop_runtime.a \
  -DPYFMI_INTEROP_TRANSPORT_INCLUDE_DIR=src/transport/include \
  -DPYFMI_INTEROP_TRANSPORT_LIBRARY=build/runtime/libpyfmi_interop_transport.a
cmake --build build/actuator_link/out
```

`PYFMI_INTEROP_CMAKE_DIR` and the runtime paths are required for every
generated project; the transport paths are required when the model's role is
not `none`. `pyfmi-interop build` passes these path variables, resolving them
for the checkout or the installed wheel, and leaves `PYFMI_INTEROP_WIRE` at its
default.

The transport library is linked whole because the UDP and TCP backends
register themselves from static initializers, and a plain archive link would
drop them. The generated project fails configuration with a clear message when
a role model is configured without the transport include directory or library:

- `PYFMI_INTEROP_TRANSPORT_INCLUDE_DIR` — directory exposing
  `pyfmi_interop/transport/*.hpp`. It is `src/transport/include` in a checkout
  and `_runtime/include` in a wheel.
- `PYFMI_INTEROP_TRANSPORT_LIBRARY` — path to
  `libpyfmi_interop_transport.a` (`.lib` on Windows). The top-level build writes
  it to `build/runtime/`.

`pyfmi-interop build` resolves both automatically for a role model and keeps
passing only the runtime for a `none` model.

The transport is selected at run time by `PYFMI_INTEROP_TRANSPORT`, whose URI
selects the backend and endpoint:

- `loopback` — in-process, the default;
- `udp://<bind-host>:<port>[?peer=<host>:<port>]` — one datagram per frame;
- `tcp://<bind-host>:<port>[?peer=<host>:<port>]` — stream transport.

A port of `0` asks the OS for an ephemeral port. A model that declares the
parameter interface takes `transport`, `bind_address`, and `peer_address` from
its FMI parameters; the environment is the fallback only when no parameter
interface is declared. Those parameters are initialization configuration and
never wire fields; the write window is stated once in the byte-transport
contract (`docs/breakdown/01-product/adapter-contract.md`). Runtime behaviour
belongs in `in` ports (`causality="input"`), not parameters.
`PYFMI_INTEROP_TRANSPORT_ENDPOINT`
is the legacy suffix for a bare scheme name. The full grammar, framing, and
validation rules are in `docs/wire.md`.

`generate` writes `--serialization` into `model.json`; `package` reads it and
bundles only that backend's artifacts. Every FMU also carries
`resources/transport.json`, which documents the default transport, the
parameter keys, and the `PYFMI_INTEROP_TRANSPORT` environment fallback.
`queue_depth` and `deadline_s` are listed there among the recognised keys, but
the C++ runtime does not consume them; only `transport`, `bind_address`, and
`peer_address` affect the selected transport.

## Package

```bash
pyfmi-interop package build/actuator_link \
  --library build/actuator_link/build/libActuatorLink.so \
  --out build/actuator_link.fmu
```

Packaging writes `modelDescription.xml` and a deterministic `.fmu` archive. The
archive carries the binary and the wire schema bundle under
`binaries/<platform>/`, and the canonical `model.json` and `runtime.json` under
`resources/`. Equal inputs produce byte-identical archives: entries are sorted,
file modes and timestamps are fixed, and the model GUID is stable.

`package` needs both the generated model directory, for the IR and names, and
the built shared library. The library must exist and match the model name.

## CLI reference

| Command | Purpose |
| --- | --- |
| `pyfmi-interop transports` | List the byte transport names (`loopback`, `udp`, `tcp`). |
| `pyfmi-interop serializations` | List the payload backends (`protobuf`, `packed`, `opaque`). |
| `pyfmi-interop inspect --model-json PATH` | Load and validate IR JSON and print the model summary. |
| `pyfmi-interop schema --model-json PATH --out DIR [--serialization NAME]` | Emit the selected backend's schema bundle (`wire.json`, plus `<Model>.proto` for protobuf). |
| `pyfmi-interop generate --model-json PATH --out DIR [--serialization NAME] [--role ROLE]` | Generate C++ from IR JSON. |
| `pyfmi-interop build DIR [--build-dir DIR]` | Configure and build a generated model with CMake. |
| `pyfmi-interop package DIR --library PATH --out FILE.fmu` | Write the FMI 2.0 description and deterministic FMU archive. |

Handled model, input, and build errors print `error: <message>` on stderr and
exit 1; argument errors use the argparse exit code. Run
`pyfmi-interop <command> --help` for the exact options of the installed
version.

## FMI XML notes

- The document is FMI 2.0 with exactly one `CoSimulation` element.
- The FMI `modelIdentifier` is the generated model name; the binary in the
  archive uses the same stem.
- Every scalar variable has a unique name and a value reference taken from the
  IR. Value references are assigned once, gap-free, in canonical signal order.
- The GUID is the stable uuid5 of the model name in the realtime namespace.
  Rebuilding the same model keeps its identity.
- No generation timestamp is written; archive timestamps are fixed, not read
  from the wall clock.
- The archive places `modelDescription.xml` at the root, the binary and wire
  schema bundle under `binaries/<platform>/`, and the IR and runtime
  descriptions under `resources/`.
- `ModelStructure/Outputs` lists the output variables in index order; optional
  FMI features that the IR does not author are absent rather than emitted as
  placeholders.

## Development

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
ruff check src tests
python -m pytest -m "not sysml"
```

`python -m pytest` runs the full suite. The `sysml` marker stays declared for
suites that opt into it, though this repository no longer ships SysML tests.
CI runs `-m "not sysml"` on Python 3.11 and 3.12 after building the runtime;
`slow` remains an orthogonal qualifier for long native runs. The moved SysML
ingestion and end-to-end tests live in `pyfmi_sysml`.
