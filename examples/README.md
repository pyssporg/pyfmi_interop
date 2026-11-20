# Examples

Checked-in examples are inputs, not build output. `adapter/` is a SysML v2 part
definition driven through the Python API into an adapter `.fmu`. `system/`
packages one selected unit, or every unit, from a multi-unit architecture. No
binaries, generated sources, or `.fmu` archives are checked in.

| Example | Input | Model | Step | Signals |
| --- | --- | --- | --- | --- |
| `adapter/` | SysML v2 | `ActuatorLink` | none (master-driven) | `Command` in (Real, Integer, Boolean, `Real[3]`) and `Feedback` out (Real, Integer, Boolean, `Real[2]`) |
| `system/` | SysML v2 | `ActuatorLink`, `SensorLink`, `Controller` | none (master-driven) | one FMU per unit; the unmarked `System` container is never packaged |

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

## One unit or all units

`system/bench.sysml` declares three `:> FmuInterop` leaves and one unmarked
container. The Python API has two packaging modes; the CLI has neither
selector, because `generate` exports only the single selected unit.

```bash
# One unit: --unit may be omitted when exactly one exists.
python examples/system/build_one.py --unit Controller --serialization packed \
  --out build/examples/system/controller

# Every unit: fmu_units() enumerates the leaves, one FMU each.
python examples/system/build_all.py --serialization packed \
  --out build/examples/system/all
```

One mode writes `<out>/model`, `<out>/build`, and `<out>/<unit>.fmu`; all-units
mode writes `<out>/<unit>/model`, `<out>/<unit>/build`, and
`<out>/<unit>/<unit>.fmu`. Parameters
(`transport`, `bind_address`, `peer_address`) are initialization-only; inputs
carry runtime behaviour. See `system/README.md`.

IR JSON (`ModelDefinition`) remains a supported `generate` and `inspect` input;
the format is described in `docs/usage.md`.
