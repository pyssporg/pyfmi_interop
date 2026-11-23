# pyfmi_interop examples

Build a two-signal `ModelSpec` plus one parameter into a packaged FMI 2.0
Co-Simulation FMU, without SysML.

## Run

From the workspace root, in the workspace venv:

```bash
python repos/pyfmi_interop/examples/core/compile_model.py
```

That is the whole example: it builds the `ModelSpec` by hand, generates the
C++, builds the native model, and packages `core_demo.fmu`. Everything lands
under the gitignored `build/examples/core/`:

| Path | What |
| --- | --- |
| `build/examples/core/` | generated C++ sources, CMake files, wire schema |
| `build/examples/core/build/libcore_demo.so` | native model library |
| `build/examples/core/core_demo.fmu` | packaged FMI 2.0 CoSimulation FMU |

Expected output:

```text
build/examples/core
build/examples/core/build/libcore_demo.so
build/examples/core/core_demo.fmu
```

Pass `--out DIR` to write elsewhere.

## Setup

The workspace venv plus the native runtime build:

```bash
python -m venv .venv-experimental
source .venv-experimental/bin/activate
pip install --no-deps -r requirements-experimental.txt
pip install -r requirements-thirdparty.txt
cmake -S repos/pyfmi_interop -B repos/pyfmi_interop/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build repos/pyfmi_interop/build
```

`cmake`, `ninja`, `g++` and `protoc` must be on `PATH`. `compile_model` links
against the static runtime produced by the CMake build.
