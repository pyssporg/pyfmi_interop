# pyfmi_interop

`pyfmi_interop` owns bytes only: it takes a model interface and puts it on one
versioned wire format, with a Python end and a C++ end. The canonical payload is
protobuf; the framing around it — length, CRC32, and format version — is this
repository's own contract. The project does not interpret the model it carries.

## Architecture

```text
Interface specification (IR JSON / ModelSpec)
        ▼
ModelSpec — the public interface contract
        │  core/codegen/ — typed signals, user_step, factory
        ▼
Generated C++17 model + per-model CMakeLists.txt
        │  core/builder.py — CMake
        ▼
Static runtime + model library
        │  core/packaging.py — FMI 2.0 modelDescription.xml + deterministic zip
        ▼
FMI 2.0 CoSimulation .fmu

Wire format: a 56-byte length + CRC32 + payload-format frame carrying an
opaque, protobuf, or packed payload.
```

The Python layer is SysML-free and lives in `core/`. It holds `spec.py`
(`ModelSpec`, `BuildConfig`), `ir.py`, `timing.py`, `wire/`, `serialization/`,
`codegen/`, `builder.py`, `packaging.py`, `pipeline.py`, and `adapter.py` (the
adapter model and its `pyfmi_interfaces` FMI layer); `cli.py` sits at the package
root. `core/serialization/` is the payload seam: `protobuf` (canonical),
`packed` (deterministic little-endian, dependency-free), and `opaque` (caller
bytes). The old module paths remain as re-export-only compatibility facades.
SysML ingestion and the parse-once adapter flow live in `pyfmi_sysml`. The C++
layer in `src/runtime/` owns the
`ModelRuntime` interface, the fixed-step realtime scheduler, the wire codec,
and the types it shares with the Python end; `src/transport/` holds the UDP and
TCP backends.

Each artifact owns one FMI facade: the core emits the interop facade, and the
adapter takes its FMI interface, headers, and model description from
`pyfmi_interfaces`. Both export the same `fmi2*` ABI, so they never share a binary.

## Install

From a checkout, build the native runtime first, then install the Python
package in editable mode:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build

python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

The wheel carries the static runtime
`_runtime/libpyfmi_interop_runtime.a`, the transport archive
`_runtime/libpyfmi_interop_transport.a`, the public headers under
`_runtime/include/`, and the shared CMake module `_runtime/cmake/wire.cmake`.
Both native archives must exist before the wheel is built. An editable install
does not require them, but generated models have no runtime to link until
`build/runtime/` holds the archives.

`pyfmi-interfaces` is a runtime dependency: the adapter takes its FMI interface,
headers, and model description from it. The package has no `[sysml]` extra and
no SysML dependency.

## Quickstart

Build a `ModelSpec` by hand and compile it in one call:

```bash
python examples/core/compile_model.py /tmp/pyfmi_core_demo
```

The same pipeline starts from IR JSON through the CLI:

```bash
pyfmi-interop transports
pyfmi-interop serializations
pyfmi-interop generate --model-json model.json --out build/model
pyfmi-interop build build/model
```

A SysML v2 source is ingested by the separate `pyfmi_sysml` composition layer,
which parses once, maps the reduction to a `ModelSpec`, and calls the interop
generator and `generate_adapter`. See the `pyfmi_sysml` documentation and
examples for the source-to-adapter chain.

## Composition layer

`pyfmi_sysml` owns the SysML reader (`pycps_sysml2`), the parser-free
`Reduction` hand-off, export selection, the `PyfmiInterop` vocabulary usage,
`includes=` package roots, and the `pyfmi-sysml` command line. The interop
`core/adapter.py` still owns the adapter model, its wire and schema output, and
its `pyfmi_interfaces` FMI layer; the composition layer calls it with a
`Reduction` and a `ModelSpec`.

Export selection is leaf-only among `:> FmuModel` candidates: a shared base such
as `FmuInterop :> FmuModel` is a role, not an FMU. On the interop side,
`adapter_from_reduction(..., component=...)` selects among several exported
leaves. The `pyfmi-interop` CLI has no `--sysml`, `--include`, or `--step-size`
options and consumes IR JSON only.

Deployment parameters are initialization configuration: `InteropDeployment`
members are FMI `causality="parameter"`, `variability="fixed"`, writable before
`fmi2EnterInitializationMode`, and never wire fields. Runtime behaviour belongs
in `in` ports (FMI `causality="input"`), not parameters.

## Wire format

- **Payload:** protobuf is the canonical schema for the model interface and the
  sample values; `packed` is a deterministic little-endian alternative and
  `opaque` carries caller bytes. The schema carries a version and changes by
  version, never in place.
- **Framing (v2):** every message has a 56-byte header, CRC32 checks, and an
  explicit `payload_format` tag (`0` opaque, `1` protobuf, `2` packed).
  Framing is the only layer this repository defines beyond the payload.
- **Ends:** a Python end and a C++ end share one set of conformance byte
  vectors, and both must reproduce them.
- **Non-goals:** protocol bindings, radio or medium models, time management,
  mission coordination, the federation-endpoint role, and an adapter catalogue.

## Development

```bash
cmake --build build
ctest --test-dir build --output-on-failure
ruff check src tests
python -m pytest -m "not sysml"
```

The default gate is `python -m pytest -m "not sysml"`; the `sysml` marker stays
declared for suites that opt into it, though this repository no longer ships
SysML tests. See `docs/breakdown/04-verification/` for the test ladder and
`AGENTS.md` for the contributor rules.

## Documentation

- `docs/architecture.md` — layers, data flow, and realtime design.
- `docs/wire.md` — envelope layout, model id, CRC32, and the schema bundle.
- `docs/usage.md` — install, generate, build, package, and CLI reference.
- `docs/breakdown/README.md` — current-state product breakdown.
- `examples/README.md` — checked-in core example.
