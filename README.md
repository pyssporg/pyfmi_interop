# pyfmi_interop

`pyfmi_interop` owns bytes only: it takes a model interface and puts it on one
versioned wire format, with a Python end and a C++ end. The canonical payload is
protobuf; the framing around it — length, CRC32, and format version — is this
repository's own contract. The project does not interpret the model it carries.

## Architecture

```text
SysML v2 definition (.sysml)
        │  sysml.py — pycps_sysml2 + pyfmi_sysml2 ingestion
        ▼
ModelDefinition IR — signals, value references, rates
        │  codegen/ — typed signals, user_step, factory
        ▼
Generated C++17 model + per-model CMakeLists.txt
        │  builder.py — CMake
        ▼
Static runtime + model library
        │  packaging.py — FMI 2.0 modelDescription.xml + deterministic zip
        ▼
FMI 2.0 CoSimulation .fmu

Wire format: a 56-byte length + CRC32 + payload-format frame carrying an
opaque, protobuf, or packed payload.
```

The Python layer is split into `ir.py`, `sysml.py`, `timing.py`, `codegen/`,
`serialization/`, `builder.py`, `packaging.py`, and `cli.py`. `serialization/`
is the payload seam: `protobuf` (canonical), `packed` (deterministic
little-endian, dependency-free), and `opaque` (caller bytes). The C++ layer in
`src/runtime/` owns the `ModelRuntime` interface, the fixed-step realtime
scheduler, the wire codec, and the types it shares with the Python end;
`src/transport/` holds the UDP and TCP backends.

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

SysML ingestion is optional at install time and required by the Quickstart
chain. In a workspace that provides `pycps-sysml2` and `pyfmi-sysml2`, install
the extra with `pip install -e ".[sysml]"`.

## Quickstart

The full chain runs from SysML v2 to a packaged adapter FMU — load, generate,
build, package — through the Python API:

```bash
pyfmi-interop transports
pyfmi-interop serializations
python examples/adapter/generate_adapter_fmu.py --serialization protobuf
```

The example is `examples/adapter/actuator_link.sysml`: a part definition with
`Command` inputs and `Feedback` outputs. The adapter has no step of its own;
the master owns the cadence. The script writes the generated sources, the build
tree, and the `.fmu` under `build/examples/adapter/<serialization>/`.
`--serialization packed` selects the dependency-free payload, and `--sysml`,
`--include`, `--name`, `--step-size`, and `--role` override the inputs; see
`examples/adapter/README.md`. Run `pyfmi-interop <command> --help` for the
individual steps.

## Shared SysML vocabulary

The wheel ships the `PyfmiInterop` library as package data;
`from pyfmi_interop import interop_definitions` returns its path. A model opts
in with `private import PyfmiInterop::*;` and gets `FmuInterop :> FmuModel`
(`interop_meta` plus the inherited `in port parameters : InteropDeployment;`)
and the loopback/`127.0.0.1:5000` deployment defaults. `load_model` and the
`psysml2` generation path add the library to the load roots only when the model
imports `PyfmiInterop`, so a model that does not import it sees no extra
candidate.

A model may also live across packages: pass the library file or directory to
`load_model(..., includes=[...])`, and repeat `--include PATH` on
`pyfmi-interop generate --sysml ...`. The extra roots go to the IR load and to
the `psysml2` reparse, so an app file that only imports a library still selects
the library's exported leaf.

`InteropMetadata` (`source`, `serialization`, `version`, all String) does not
inherit `FmuMetadata`, and no generator consumes it yet; it does not change
`modelDescription.xml` or the wire.

Export selection is leaf-only among `:> FmuModel` candidates: a shared base such
as `FmuInterop :> FmuModel` is a role, not an FMU. Imported definitions are
selectable, so a library-defined leaf is the export unit and a direct FMU is
packaged under its bare name. On the Python side, `composition=` can name a
base explicitly, and the `psysml2` adapter API's `component=` selects among
several exported leaves; the `pyfmi-interop` CLI exposes neither and exports
the single unit the loader selects.

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
python -m pytest -m "not slow"
```

The default test gate excludes `slow`; the full suite is
`python -m pytest`. See `docs/breakdown/04-verification/` for the test ladder
and `AGENTS.md` for the contributor rules.

## Documentation

- `docs/architecture.md` — layers, data flow, and realtime design.
- `docs/wire.md` — envelope layout, model id, CRC32, and the schema bundle.
- `docs/usage.md` — install, generate, build, package, and CLI reference.
- `docs/breakdown/README.md` — current-state product breakdown.
- `examples/README.md` — checked-in SysML example.
