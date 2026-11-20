# Examples

Checked-in examples are inputs, not build output. `adapter/` is a SysML v2 part
definition driven through the Python API into an adapter `.fmu`. No binaries,
generated sources, or `.fmu` archives are checked in.

| Example | Input | Model | Step | Signals |
| --- | --- | --- | --- | --- |
| `adapter/` | SysML v2 | `ActuatorLink` | none (master-driven) | `Command` in (Real, Integer, Boolean, `Real[3]`) and `Feedback` out (Real, Integer, Boolean, `Real[2]`) |

On the default `psysml2` layer the FMI model identifier, shared library, proto,
and `.fmu` use `ActuatorLink`; the script's default `--name`
(`ActuatorLinkAdapter`) is recorded as `model_name` in `resources/runtime.json`.
The adapter has no step of its own: the master owns the cadence.

## Run the example

From the repository root, after building the native runtime and installing the
package with the `sysml` extra:

```bash
python examples/adapter/generate_adapter_fmu.py --serialization protobuf
```

The script runs the whole chain — `load_model`, `generate_model`, `build_model`,
`package_fmu` — and writes under `build/examples/adapter/<serialization>/`,
which is ignored by Git. Use `--serialization packed` for the dependency-free
payload; see `adapter/README.md` for the FMU and wire details.

IR JSON (`ModelDefinition`) remains a supported `generate` and `inspect` input;
the format is described in `docs/usage.md`.
