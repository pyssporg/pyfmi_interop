# Examples

Checked-in examples are inputs, not build output. Each one is a small IR JSON
model that the CLI can inspect, generate from, build, and package without a
SysML dependency. No binaries, generated sources, or `.fmu` archives are
checked in.

| Example | Model | Step | Signals |
| --- | --- | --- | --- |
| `loopback/` | `LoopbackModel` | 1 kHz | one real input `u`, one real output `y` |

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
