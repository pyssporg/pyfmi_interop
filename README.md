# pyfmi_interop

`pyfmi_interop` owns bytes only: it takes a model interface and puts it on one
versioned wire format, with a Python end and a C++ end. The payload is
protobuf; the framing around it — length, CRC32, and format version — is this
repository's own contract. The project does not interpret the model it carries.

## Architecture

```text
SysML v2 definition (.sysml)
        │  sysml.py — pycps_sysml2 + pyfmi_sysml2 ingestion
        ▼
ModelDefinition IR — signals, value references, rates, transport bindings
        │  codegen/ — typed signals, binding hooks, user_step, factory
        ▼
Generated C++17 model + per-model CMakeLists.txt
        │  builder.py — CMake
        ▼
Static runtime + model library
        │  packaging.py — FMI 2.0 modelDescription.xml + deterministic zip
        ▼
FMI 2.0 CoSimulation .fmu

Wire format: protobuf payload in length + CRC32 + format-version frames.
```

The Python layer is split into `ir.py`, `sysml.py`, `timing.py`, `codegen/`,
`builder.py`, `packaging.py`, and `cli.py`. The C++ layer in `runtime/` owns the
`ModelRuntime` interface, the fixed-step realtime scheduler, and the types the
wire codec shares with the Python end. The adapter catalogue and its
compile-gated stubs are removed by the wire-format work.

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
`_runtime/libpyfmi_interop_runtime.a` and the public headers under
`_runtime/include/`. The native runtime must exist before the wheel is built;
an editable source install follows the same rule.

SysML ingestion is optional. In a workspace that provides `pycps-sysml2` and
`pyfmi-sysml2`, install the extra with `pip install -e ".[sysml]"`. A plain IR
JSON input needs no SysML dependency.

## Quickstart

```bash
pyfmi-interop adapters
pyfmi-interop inspect --model-json examples/loopback/model.json
pyfmi-interop generate --model-json examples/loopback/model.json --out build/loopback
pyfmi-interop build build/loopback
pyfmi-interop package build/loopback \
  --library build/loopback/build/libLoopbackModel.so \
  --out build/loopback.fmu
```

The example is a 1 kHz model with one real input (`u`), one real output (`y`),
and one loopback binding. Run `pyfmi-interop <command> --help` for the
exact options of an installed build.

## Wire format

- **Payload:** protobuf is the canonical schema for the model interface and the
  sample values. The schema carries a version and changes by version, never in
  place.
- **Framing:** every message is length-delimited, CRC32-checked, and tagged
  with the format version. Framing is the only layer this repository defines
  beyond the payload.
- **Ends:** a Python end and a C++ end share one set of conformance byte
  vectors, and both must reproduce them.
- **Non-goals:** HLA/RTI conformance, DCP, ED-247, ROS 2, DIS as a canonical
  vocabulary, radio or medium models, time management, mission coordination,
  the federation-endpoint role, and an adapter catalogue.

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
- `docs/adapters.md` — legacy adapter catalogue, removed when `docs/wire.md`
  lands.
- `docs/usage.md` — install, generate, build, package, and CLI reference.
- `docs/breakdown/README.md` — current-state product breakdown.
- `examples/README.md` — checked-in IR examples.
