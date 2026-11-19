# Adapter FMU from SysML (Python API)

This example authors a SysML v2 part definition and runs the whole pipeline in
Python — load, generate, build, package — with no CLI and no IR JSON.

## What the SysML says

`actuator_link.sysml` defines one package, three port definitions, one part
definition, one parameter set, and the composition root:

| Port | Direction on the part | Fields |
| --- | --- | --- |
| `Command` | `in` | `setpoint : Real`, `mode : Integer`, `enable : Boolean`, `gains : Real[3]` |
| `Feedback` | `out` | `position : Real`, `status : Integer`, `healthy : Boolean`, `samples : Real[2]` |
| `InteropDeployment` | parameter interface | `transport`, `bind_address`, `peer_address`, `queue_depth` |

`part def ActuatorLink` owns `in port command : Command;`,
`out port feedback : Feedback;`, and `in port parameters : InteropDeployment;`.
`part def Root` is the composition root that makes `ActuatorLink` the exported
component and binds the partial `BenchDefaults :> ParameterSet` to
`link.parameters`.

A port field with fixed multiplicity is not an FMI array — FMI 2.0 has no array
variable — so it becomes one scalar variable per element. `command.gains[0..2]`
becomes `command_gains_0` through `command_gains_2` on the wire and three
separate `ScalarVariable` entries in `modelDescription.xml`.

## Three classes of value

| Class | Examples | Where it lives | On the wire? |
| --- | --- | --- | --- |
| Build-time attribute | serialization backend, derived role (`step_size_s` belongs to the realtime model, not the adapter) | authored/generated into the build; changing it requires a rebuild | no |
| Deployment parameter | `transport`, `bind_address`, `peer_address`, `queue_depth`, `deadline_s` | FMI `causality="parameter"`, `variability="fixed"` with an authored `start` | never |
| Derived | value reference, field number, wire direction, model id | computed from the interface by the generators | yes (model id is in the envelope header) |

Parameters are configuration, not wire fields. They are omitted from `wire.json`,
from the protobuf schema and packed layout, and from the `model_id` digest. The
remaining INPUT/OUTPUT fields keep the value references they were assigned, and
each wire field number stays equal to its value reference.

## Wire direction is the inverse of FMI causality

The FMI XML describes what the model exposes; the wire describes what the
endpoint sends.

| FMI causality | Adapter role | Wire direction |
| --- | --- | --- |
| `input` | publish | `out` |
| `output` | consume | `in` |
| `parameter` | configuration | never published |

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
resources/transport.json                 parameter keys, schemes, env fallback
```

`packed` ships the same layout minus the `.proto`; `wire.json` alone describes
its deterministic little-endian payload. The generated source tree (including
`wire.json` and, for protobuf, the `.proto`) is also written to the model
directory before the build.

## Override a deployment parameter

The parameter variables are ordinary FMI variables with
`causality="parameter"` and `variability="fixed"`. Read their value references
from `modelDescription.xml` (or `resources/model.json`) and write them with the
matching setter *before* `fmi2EnterInitializationMode`:

```c
/* transport, bind_address and peer_address are String parameters. */
fmi2SetString(component, transport_vr, 1, (const fmi2String[]){"udp"});
fmi2SetString(component, bind_vr, 1, (const fmi2String[]){"127.0.0.1:5000"});
fmi2SetString(component, peer_vr, 1, (const fmi2String[]){"127.0.0.1:5001"});
/* queue_depth is an Integer parameter. */
fmi2SetInteger(component, queue_depth_vr, 1, (const fmi2Integer[]){8});

fmi2EnterInitializationMode(component);   /* the transport is opened here */
fmi2ExitInitializationMode(component);
```

The runtime composes `<transport>://<bind_address>`, appends
`?peer=<peer_address>` when the peer is non-empty, and treats
`transport=loopback` or an empty `bind_address` as `loopback`. Parameter names
are matched case-insensitively without the port prefix. An unknown `transport`
value makes `fmi2EnterInitializationMode` return `fmi2Error` and log the key and
the accepted values (`loopback`, `udp`, `tcp`). Writing a parameter after
initialization is rejected with `fmi2Error`; writes in the instantiated state are
legal.

Because the transport is created per instance from parameter members, two
instances of the same FMU in one process can bind different addresses. The
process-global `PYFMI_INTEROP_TRANSPORT` / `PYFMI_INTEROP_TRANSPORT_ENDPOINT`
variables remain only as a fallback for a model that declares no parameter
interface at all.

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

Configure this FMU through its parameters as shown above. Give the peer the
address it should bind or send to according to its own role. A UDP peer that
consumes the adapter's published `command` fields binds a socket and receives
frames; the frame carries the payload whose schema is
`binaries/linux64/ActuatorLinkAdapter.proto` inside the `.fmu` for `protobuf`.
Extract that file and compile it into the peer. For `packed` there is no
`.proto`: the peer reads `binaries/linux64/wire.json` and reproduces the packed
layout in value-reference order.
