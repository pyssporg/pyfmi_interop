# Loopback example

`model.json` is a minimal realtime model: 1 kHz fixed step, one real input
`u` (value reference 0) and one real output `y` (value reference 1). The rate
group covers both signals with a 0.5 ms deadline inside the 1 ms period.

```text
u ──► [ user_step ] ──► y
           1 kHz
```

The JSON is the canonical `ModelDefinition` form: signals are sorted by name,
value references are gap-free, and the GUID is the stable uuid5 of the model
name. It carries no equations; a generated model leaves `user_step` to the
user.

## Use it

```bash
pyfmi-interop inspect --model-json examples/loopback/model.json
pyfmi-interop generate --model-json examples/loopback/model.json --out build/loopback
pyfmi-interop build build/loopback
pyfmi-interop package build/loopback \
  --library build/loopback/build/libLoopbackModel.so \
  --out build/loopback.fmu
```

`inspect` validates the model and prints the resolved signals.
`generate` writes the C++ source and `CMakeLists.txt`; `build` compiles them
against the static runtime; `package` writes the FMI 2.0 CoSimulation archive.
