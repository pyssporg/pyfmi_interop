# Examples

Checked-in examples are inputs, not build output. `loopback/` is a small IR
JSON model that the CLI can inspect, generate from, build, and package without
a SysML dependency; `adapter/` is a SysML v2 part definition driven through the
Python API into an adapter `.fmu`. No binaries, generated sources, or `.fmu`
archives are checked in.

| Example | Input | Model | Step | Signals |
| --- | --- | --- | --- | --- |
| `loopback/` | IR JSON | `LoopbackModel` | 1 kHz | one real input `u`, one real output `y` |
| `adapter/` | SysML v2 | `ActuatorLinkAdapter` | 1 kHz | `Command` in (Real, Integer, Boolean, `Real[3]`) and `Feedback` out (Real, Integer, Boolean, `Real[2]`) |

## Run an example

From the repository root, after building the native runtime and installing the
package:

```bash
pyfmi-interop inspect --model-json examples/loopback/model.json
pyfmi-interop generate --model-json examples/loopback/model.json --out build/loopback
pyfmi-interop build build/loopback
pyfmi-interop package build/loopback \
  --library build/loopback/build/libLoopbackModel.so \
  --out build/loopback.fmu
```

Build output stays under `build/`, which is ignored by Git. The IR JSON format
is the `ModelDefinition` serialization described in `docs/usage.md`.

The adapter example generates, builds, and packages an FMU from SysML with the
Python API instead of the CLI; see `adapter/README.md`:

```bash
python examples/adapter/generate_adapter_fmu.py --serialization protobuf
```
