# Examples

Checked-in examples are inputs, not build output. `core/` drives a `ModelSpec`
directly through the SysML-free API. No binaries, generated sources, or `.fmu`
archives are checked in. The SysML v2 examples moved to `pyfmi_sysml`.

| Example | Input | Model | Step | Signals |
| --- | --- | --- | --- | --- |
| `core/` | Python `ModelSpec` | `core_demo` | 1 ms | one input, one output, one parameter |

## Run the core example

From the repository root, after building the native runtime:

```bash
python examples/core/compile_model.py /tmp/pyfmi_core_demo
```

The script builds a two-signal `ModelSpec` plus one parameter, then prints the
source directory, the native library, and the packaged `.fmu`. It imports only
`pyfmi_interop.core`, so no SysML packages are needed.

IR JSON (`ModelDefinition`) is a supported `generate` and `inspect` input; the
format and the CLI are described in `docs/usage.md`.

## SysML v2

SysML ingestion, export selection, and the source-to-adapter chain live in the
separate `pyfmi_sysml` package; its `examples/sysml/` directory carries the
adapter and multi-unit examples.
