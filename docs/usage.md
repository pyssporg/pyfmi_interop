# Usage

`pyfmi-distributed` turns a SysML v2 model or an IR JSON file into generated
C++17 sources, builds them with CMake, and packages the result as an FMI 2.0
CoSimulation FMU.

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
`pip install pyfmi_distributed-<version>-py3-none-<platform>.whl`. The wheel
carries the prebuilt static runtime and public headers; it cannot be built
without the native runtime in `build/runtime/`.

SysML ingestion needs the optional dialect packages:

```bash
pip install -e ".[sysml]"
```

In the pyssp workspace those packages are installed editable from the sibling
checkouts rather than resolved from an index. IR JSON input needs no SysML
packages.

## Inputs

`generate` accepts either a SysML v2 source or an IR JSON file, selected by
`--sysml` or `--model-json`.

- **SysML v2** — a `.sysml` file, ingested through `sysml.py` and
  `pycps_sysml2` / `pyfmi_sysml2`. `--step-size` sets the base step for the
  generated IR, and `--name` overrides the model name.
- **IR JSON** — canonical `ModelDefinition` JSON, as written by `ir.py` and
  shown in `examples/loopback/model.json`. It carries the same fields the
  generator consumes after ingestion, so it is the direct path for tests and
  for tools that build the IR themselves.

Run `inspect` first to validate the IR and see the resolved signal table
without emitting anything:

```bash
pyfmi-distributed inspect --model-json examples/loopback/model.json
```

## Generate

```bash
pyfmi-distributed generate --model-json examples/loopback/model.json \
  --out build/loopback
```

Generation emits a small C++17 project: `model_runtime.hpp`,
`model_runtime.cpp`, `model_impl.hpp`, `bindings.cpp`, `model.json`, and
`CMakeLists.txt`. The source contains typed signal members, value-reference
accessors, publish/consume hooks for the bindings, the `user_step` hook, and the
`pyfmi_distributed_create_model` factory.

`model_impl.hpp` holds the empty `user_step` hook and is the one generated file
meant to be edited for model equations. Everything else is build output: change
the IR or a generator template and regenerate rather than hand-editing it.

## Build

```bash
pyfmi-distributed build build/loopback
```

The build configures the per-model `CMakeLists.txt` in
`build/loopback/build/` and links the generated source against the static
runtime. Pass adapter CMake definitions when a compile-gated adapter is
intentionally enabled:

```bash
cmake -S build/loopback -B build/loopback/out \
  -DPYFMI_DIST_ENABLE_HLA=ON \
  -DPYFMI_DIST_RUNTIME_INCLUDE_DIR=runtime/include \
  -DPYFMI_DIST_RUNTIME_LIBRARY=build/runtime/libpyfmi_distributed_runtime.a
cmake --build build/loopback/out
```

The loopback adapter is always available. The other adapters remain stubs
unless their option is ON and their protocol library is present; see
`docs/adapters.md`.

Enabling a gated adapter acquires the prebuilt upstream library from an
installed package (vcpkg or system) first, then a `third_party/<lib>`
submodule, then FetchContent with `-DPYFMI_DIST_ALLOW_FETCH=ON`. The vcpkg
features are declared in `vcpkg.json`; ROS 2 comes from a system Jazzy
installation only. The dependency table and exact commands are in
`docs/adapters.md`.

## Package

```bash
pyfmi-distributed package build/loopback \
  --library build/loopback/build/libLoopbackModel.so \
  --out build/loopback.fmu
```

Packaging writes `modelDescription.xml` and a deterministic `.fmu` archive. The
archive carries the binary under `binaries/<platform>/` and the canonical
`model.json`, `runtime.json`, and `adapters.json` under `resources/`. Equal
inputs produce byte-identical archives: entries are sorted, file modes and
timestamps are fixed, and the model GUID is stable.

`package` needs both the generated model directory, for the IR and names, and
the built shared library. The library must exist and match the model name.

## CLI reference

| Command | Purpose |
| --- | --- |
| `pyfmi-distributed adapters` | List the adapter catalogue, kind, availability, and external requirement. |
| `pyfmi-distributed inspect --model-json PATH` | Load and validate IR JSON and print the model summary. |
| `pyfmi-distributed generate --model-json PATH --out DIR` | Generate C++ from IR JSON. |
| `pyfmi-distributed generate --sysml PATH --out DIR [--step-size S] [--name NAME]` | Generate C++ from SysML v2. |
| `pyfmi-distributed build DIR [--build-dir DIR]` | Configure and build a generated model with CMake. |
| `pyfmi-distributed package DIR --library PATH --out FILE.fmu` | Write the FMI 2.0 description and deterministic FMU archive. |

Handled model, input, and build errors print `error: <message>` on stderr and
exit 1; argument errors use the argparse exit code. Run
`pyfmi-distributed <command> --help` for the exact options of the installed
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
- The archive places `modelDescription.xml` at the root, the binary under
  `binaries/<platform>/`, and the IR and runtime descriptions under
  `resources/`.
- `ModelStructure/Outputs` lists the output variables in index order; optional
  FMI features that the IR does not author are absent rather than emitted as
  placeholders.

## Development

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
ruff check src tests
python -m pytest -m "not slow"
```

`python -m pytest` runs the full suite, including the slow native end-to-end
tests. CI runs the non-slow subset on Python 3.11 and 3.12 after building the
runtime.
