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
`--name`, `--step-size`, and `--role` override the inputs; see
`examples/adapter/README.md`. Run `pyfmi-interop <command> --help` for the
individual steps.

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
