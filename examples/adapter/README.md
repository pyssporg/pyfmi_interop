# Adapter FMU from SysML (Python API)

This example authors a SysML v2 part definition and runs the whole pipeline in
Python — load, generate, build, package — with no CLI and no IR JSON.

## What the SysML says

`actuator_link.sysml` defines one package, two port definitions, and one part
definition:

| Port | Direction on the part | Fields |
| --- | --- | --- |
| `Command` | `in` | `setpoint : Real`, `mode : Integer`, `enable : Boolean`, `gains : Real[3]` |
| `Feedback` | `out` | `position : Real`, `status : Integer`, `healthy : Boolean`, `samples : Real[2]` |

`part def ActuatorLink` owns `in port command : Command;` and
`out port feedback : Feedback;`. `part def Root` is only the composition root
that makes `ActuatorLink` the exported component. The model uses only the
subset `pycps_sysml2` loads: `port def`, `part def`, `attribute`, and `in`/`out`
port usages.

A port field with fixed multiplicity is not an FMI array — FMI 2.0 has no array
variable — so it becomes one scalar variable per element. `command.gains[0..2]`
becomes `command_gains_0` through `command_gains_2` on the wire and three
separate `ScalarVariable` entries in `modelDescription.xml`.

## Wire direction is the inverse of FMI causality

The FMI XML describes what the model exposes; the wire describes what the
endpoint sends.

| FMI causality | Adapter role | Wire direction |
| --- | --- | --- |
| `input` | publish | `out` |
| `output` | consume | `in` |
| `parameter` | none | never published |

Because `ActuatorLink` has both inputs and outputs, the derived role is
`adapter`: the six `command.*` fields are published (`out`) and the five
`feedback.*` fields are consumed (`in`).

## Generated FMU layout

For `ActuatorLinkAdapter` on Linux the archive contains:

```text
modelDescription.xml                     FMI 2.0 variables, causalities, value references
binaries/linux64/ActuatorLinkAdapter.so  generated adapter shared library
binaries/linux64/ActuatorLinkAdapter.proto  payload schema (protobuf only)
binaries/linux64/wire.json               field table, format, role, wire directions
resources/model.json                     resolved IR (role, serialization, signals)
resources/runtime.json                   fingerprint, binary path, format id
resources/transport.json                 default transport and endpoint environment key
```

`packed` ships the same layout minus the `.proto`; `wire.json` alone describes
its deterministic little-endian payload. The generated source tree (including
`wire.json` and, for protobuf, the `.proto`) is also written to the model
directory before the build.

## Run it

From the repository root, with the native runtime built and the package
installed:

```bash
python examples/adapter/generate_adapter_fmu.py --serialization protobuf
python examples/adapter/generate_adapter_fmu.py --serialization packed
```

Both write under `build/examples/adapter/<serialization>/` (gitignored):

```text
build/examples/adapter/<serialization>/model/       generated C++ and schema
build/examples/adapter/<serialization>/build/       CMake build tree
build/examples/adapter/<serialization>/ActuatorLinkAdapter.fmu
```

Use `--out DIR` to choose another root, and `--sysml`, `--name`,
`--step-size`, or `--role` to override the inputs. The script prints the
derived role, payload message and format id, the field table, transport URI
examples, and the final `.fmu` path.

## Pointing an external peer at it

The adapter reads its transport from `PYFMI_INTEROP_TRANSPORT` in the process
that runs the FMU. Set, for example,
`PYFMI_INTEROP_TRANSPORT=udp://127.0.0.1:5000?peer=127.0.0.1:5001` for the
adapter, and give the peer the address it should bind or send to according to
its own role. A UDP peer that consumes the adapter's published `command` fields
binds a socket and receives frames; the frame carries the payload whose schema
is `binaries/linux64/ActuatorLinkAdapter.proto` inside the `.fmu` for
`protobuf`. Extract that file and compile it into the peer. For `packed` there
is no `.proto`: the peer reads `binaries/linux64/wire.json` and reproduces the
packed layout in value-reference order.
