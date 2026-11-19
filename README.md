# pyfmi_interop

Turn a SysML v2 definition of an FMU into an optimized C++17 realtime runtime
with transport adapters, then package the result as an FMI 2.0 CoSimulation
FMU. The SysML model defines the interface and the signal bindings; the model's
equations stay in the generated `user_step` hook.

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

Transport adapters: loopback (always built), HLA, DIS, DCP, ROS 2, ED-247.
```

The Python layer is split into `ir.py`, `sysml.py`, `timing.py`, `codegen/`,
`builder.py`, `packaging.py`, and `cli.py`. The C++ layer in `runtime/` owns the
`ModelRuntime` interface, the fixed-step realtime scheduler, and the `Transport`
registry. Only the loopback adapter is always compiled; the remaining adapters
are compile-gated stubs behind `PYFMI_INTEROP_ENABLE_*` and default to OFF.

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

## Adapter status

| Adapter | CMake option | Status | External requirement |
| --- | --- | --- | --- |
| loopback | none, always built | stable | none |
| HLA | `PYFMI_INTEROP_ENABLE_HLA` | stub, experimental | OpenRTI (IEEE 1516) |
| DIS | `PYFMI_INTEROP_ENABLE_DIS` | stub, experimental | open-dis-cpp |
| DCP | `PYFMI_INTEROP_ENABLE_DCP` | stub, experimental | DCPLib (ASAM X-DCP); not DDS |
| ROS 2 | `PYFMI_INTEROP_ENABLE_ROS2` | stub, experimental | `rclcpp`, system Jazzy |
| ED-247 | `PYFMI_INTEROP_ENABLE_ED247` | stub, experimental | Airbus ED247_LIBRARY |

No external protocol library is a hard build dependency. A gated-off adapter
still links and reports `available() == false`; enabling an option without the
library fails at CMake configuration or adapter initialization, not silently.

## Protocol libraries

The repository does not reimplement protocol serialization. Each adapter binds
the prebuilt upstream library through its public API: OpenRTI (HLA),
open-dis-cpp (DIS), DCPLib (ASAM X-DCP), `rclcpp` (ROS 2), and the Airbus
ED247_LIBRARY (ED-247). The dependency table, pins, licenses, CMake targets, and
acquisition rules are in `docs/adapters.md`; the vcpkg feature manifest is
`vcpkg.json`. Installed packages are preferred, then `third_party/<lib>`
submodules, then FetchContent with `-DPYFMI_INTEROP_ALLOW_FETCH=ON`; ROS 2 is a
system Jazzy installation only. The adapter bindings remain experimental
skeletons, not completed mappings.

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

- `docs/architecture.md` — layers, data flow, realtime design, adapter gating.
- `docs/adapters.md` — adapter catalogue, CMake options, and how to add one.
- `docs/usage.md` — install, generate, build, package, and CLI reference.
- `docs/breakdown/README.md` — current-state product breakdown.
- `examples/README.md` — checked-in IR examples.
