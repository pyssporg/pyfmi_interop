# Wire envelope

`pyfmi_interop.wire` defines the framing around an opaque protobuf payload: a
fixed 48-byte header, a payload, and two CRC32 checks. The payload schema and
its generated bindings are a separate contract; this module never parses the
payload and has no protobuf dependency.

* The layout is **little-endian** and packed with `struct` (`<`), so there is
  no padding and no alignment requirement.
* `HEADER_SIZE = 48` and `WIRE_VERSION = 1`.
* Encoding is deterministic: equal model, payload, `instance`, `sequence`, and
  `timestamp_ns` produce byte-identical frames.
* The codec never reads the clock. `sequence` and `timestamp_ns` are always
  caller-supplied.

## Transport boundary

A frame is transport-independent bytes. Byte transports (`udp`, `tcp`, `unix`)
carry it; this repository ships the `Transport` interface and an in-process
loopback backend for tests, not a protocol binding. Discovery, medium, and
protocol semantics belong elsewhere and never change the envelope.

## Byte layout

All multi-byte integers are unsigned little-endian.

| Offset | Width | Field | Type / value |
| ---: | ---: | --- | --- |
| 0 | 4 | magic | ASCII `PFMI` (`b"PFMI"`) |
| 4 | 2 | wire version | uint16, `1` |
| 6 | 2 | header size | uint16, `48` |
| 8 | 8 | model id | 8 raw bytes, derived below |
| 16 | 4 | instance id | uint32 |
| 20 | 8 | sequence | uint64 |
| 28 | 8 | timestamp | uint64 nanoseconds |
| 36 | 4 | payload length | uint32, bytes |
| 40 | 4 | payload CRC32 | uint32 over payload bytes only |
| 44 | 4 | header CRC32 | uint32 over header bytes `0..43` |
| 48 | *n* | payload | opaque bytes, `n` = payload length |

The header CRC field is the last header field, so it is never part of its own
input. The payload CRC is computed before the header and is carried as a normal
header field.

The equivalent Python packing is:

```python
header_prefix = struct.pack(
    "<4sHH8sIQQII",
    b"PFMI", 1, 48, model_id, instance, sequence, timestamp_ns,
    len(payload), payload_crc32,
)
header_crc32 = zlib.crc32(header_prefix) & 0xFFFFFFFF
frame = header_prefix + struct.pack("<I", header_crc32) + payload
```

`decode` also rejects a buffer that holds more bytes than the declared frame
(`TrailingBytes`) so one buffer cannot silently contain two frames.

## Model id derivation

`model_id(model)` returns the first 8 bytes of SHA-256 over this exact byte
sequence:

1. the domain separator `b"pyfmi_interop.model-id.v1\x00"`;
2. `model.name` encoded as UTF-8, followed by one NUL byte (`b"\x00"`);
3. `model.step_size_s` as an IEEE 754 double, little-endian (`struct.pack("<d", ...)`);
4. for each signal ordered by `(value_reference, name)`, one record:
   `value_reference` as uint32 little-endian, then `DataType.number` as uint8
   (`struct.pack("<IB", ...)`).

Direction, names other than the model name, units, rates, capacities, and
initial values are **not** part of the id. Adding, removing, renumbering, or
retyping a signal, changing the model name, or changing the step size changes
the id.

## CRC-32 definition

Both checks use the standard CRC-32/ISO-HDLC (IEEE 802.3), exactly what
Python's `zlib.crc32` and C's `crc32` compute:

| Parameter | Value |
| --- | --- |
| Width | 32 |
| Polynomial | `0x04C11DB7` (reflected `0xEDB88320`) |
| Initial value | `0xFFFFFFFF` |
| Input reflection (refin) | yes |
| Output reflection (refout) | yes |
| Final XOR (xorout) | `0xFFFFFFFF` |
| Check value for `"123456789"` | `0xCBF43926` |

* **Payload CRC32** covers the payload bytes only.
* **Header CRC32** covers header bytes `0..43` inclusive (magic through payload
  CRC), excluding itself and the payload.

## Error taxonomy

All derive from `WireError`; `decode` never raises a bare `struct.error`.

| Exception | Raised when |
| --- | --- |
| `WireError` | base class for every envelope failure |
| `InvalidMagic` | bytes `0..3` are not `PFMI` |
| `UnsupportedWireVersion` | wire version is not `1` |
| `InvalidHeaderSize` | header size is not `48` |
| `TruncatedFrame` | buffer is shorter than the fixed header |
| `LengthOverflow` | declared payload length overflows uint32 frame length, or the declared frame extends past the buffer |
| `TrailingBytes` | buffer holds more bytes than the declared frame |
| `ChecksumError` | base class for CRC failures |
| `HeaderChecksumError` | header CRC32 mismatch |
| `PayloadChecksumError` | payload CRC32 mismatch |
| `FieldRangeError` | an `encode` argument does not fit its field |

## Worked example

Model `demo`, step size `0.01`, signals `alpha` (id 1, real/output) and `beta`
(id 2, integer/input). Instance 7, sequence 42, timestamp
`1_700_000_000_000_000_000` ns, payload `b"hello"`:

```
50464d49 0100 3000 ee78acea761957f0
07000000 2a00000000000000 00002a36fe9c9717
05000000 86a61036 81c1ab1c
68656c6c6f
```

| Bytes | Field | Value |
| --- | --- | --- |
| `50464d49` | magic | `PFMI` |
| `0100` | wire version | 1 |
| `3000` | header size | 48 (0x30) |
| `ee78acea761957f0` | model id | derived, see above |
| `07000000` | instance | 7 |
| `2a00000000000000` | sequence | 42 |
| `00002a36fe9c9717` | timestamp | 1 700 000 000 000 000 000 ns |
| `05000000` | payload length | 5 |
| `86a61036` | payload CRC32 | `zlib.crc32(b"hello")` |
| `81c1ab1c` | header CRC32 | over bytes `0..43` |
| `68656c6c6f` | payload | `hello` |

Empty payload for the same model and header values:

```
50464d4901003000ee78acea761957f0070000002a0000000000000000002a36fe9c971700000000000000001880f4c4
```

## Schema bundle

Every packaged FMU carries the payload schema next to its binary, under
`binaries/<platform>/`:

| Artifact | Purpose |
| --- | --- |
| `<Model>.proto` | proto3 payload schema; field numbers are the signal `value_reference` ids verbatim |
| `wire.json` | JSON descriptor of the model, its derived model id, and every signal |

The bundle is a pure projection of the IR. Both artifacts are emitted twice
byte-identically: signals are ordered by `(value_reference, name)`, JSON keys
are sorted, floats use the shortest round-tripping form, and neither artifact
contains a timestamp or a filesystem path. `wire.json` records the schema
format version, model name, GUID, model id as 16 hex characters (the same
8-byte id the envelope carries), step size, `payload_message`, and
`proto_package`, followed by the ordered `signals` list
(`{id, name, data_type, direction, rate_hz, unit, capacity}`) and the
`rate_groups` list.

The `.proto` declares `package pyfmi_interop.wire;`, a shared `Value` message
with a `oneof kind` (`double real`, `sint64 integer`, `bool boolean`,
`bytes string`), and one payload message per model. Each payload field uses the
signal's IR id as its field number, so ids are never renumbered and gaps stay
gaps. The message reserves protobuf's internal range `19000 to 19999`; it does
not reserve the gaps between used ids. Each field carries a comment with the
signal name, type, direction, rate (base or Hz), unit (or `unspecified` /
`dimensionless`), and string capacity in bytes.

A third-party decoder needs only the packaged files: read `<Model>.proto` (or
compile it once) to learn the payload message name and field numbers, then read
`wire.json` to map each field id to its name, type, direction, rate, unit, and
string capacity. No Python package, SysML model, or IR file is required. The
`.proto` is a shipped artifact: a `raw` build never needs `protoc`, while a
`protobuf` build consumes the same emitted file at configure/build time (see
below). A signal that cannot be projected (an illegal protobuf field
identifier, a duplicate id, a non-finite number) raises `ProjectionError`
during packaging; it is never silently dropped.

## C++ end

The C++ implementation matches Python byte for byte. It uses the same
`<4sHH8sIQQII` field order and widths, little-endian integers, `crc32` with the
reflected IEEE 802.3 polynomial and init/xorout `0xFFFFFFFF`, the same model-id
domain separator and `<d`/`<IB` record layout, magic `PFMI`, version `1`, and
header size `48`. The CRC over `"123456789"` is `0xCBF43926`.

### Runtime files

| File | Purpose |
| --- | --- |
| `runtime/include/pyfmi_interop/runtime/wire.hpp` | `encode_frame` / `decode_frame`, `Header`, `Frame`, `ErrorCode` / `WireError`, `crc32`, `sha256`, `model_id` |
| `runtime/src/wire.cpp` | Packed little-endian envelope, CRC32/ISO-HDLC table, portable SHA-256 (no OpenSSL) |
| `runtime/include/pyfmi_interop/runtime/payload.hpp` | `PayloadCodec` interface plus the compile-time `payload_mode_name()` |
| `runtime/src/payload.cpp` | Reports the selected payload mode to dependents |

`ErrorCode` names mirror the Python taxonomy: `InvalidMagic`,
`UnsupportedWireVersion`, `InvalidHeaderSize`, `TruncatedFrame`,
`LengthOverflow`, `TrailingBytes`, `HeaderChecksumError`,
`PayloadChecksumError`, and `FieldRangeError`, with `ChecksumError` as the
shared CRC parent. `encode_frame`/`decode_frame` return a result carrying the
frame and a `WireError`; they never throw. Decode checks in the same order as
Python: truncation, magic, version, header size, header CRC32, declared length,
trailing bytes, payload CRC32.

The model id is derived with a small portable SHA-256 over the documented input.
The C++ `model_id` reproduces the Python digest for `demo`
(`ee78acea761957f0`) and `demo_model` (`983f897eb99c8464`); this parity is
asserted in `runtime/tests/test_wire.cpp`.

### Wire mode option

`PYFMI_INTEROP_WIRE` is a string cache variable with values `protobuf` and
`raw`. When it is empty (the default) CMake selects `protobuf` if libprotobuf
and `protoc` are found, otherwise `raw`, and prints the choice. The resolved
value is exposed as:

* the `PYFMI_INTEROP_WIRE_MODE` cache variable;
* the `PYFMI_INTEROP_WIRE_MODE` target property;
* the public compile definition `PYFMI_INTEROP_WIRE_PROTOBUF=1` or
  `PYFMI_INTEROP_WIRE_RAW=1`.

The logic lives in `cmake/wire.cmake` and is included by the top-level
`CMakeLists.txt` and by every generated model project. `protobuf` requires
libprotobuf and `protoc`; selecting it without them is a configure error rather
than a silent fallback. `raw` is fully supported and keeps the envelope
payload-agnostic: caller bytes are carried unchanged.

### Build both modes

```bash
cmake -S . -B build -DPYFMI_INTEROP_WIRE=protobuf
cmake --build build -j
ctest --test-dir build --output-on-failure

cmake -S . -B build-raw -DPYFMI_INTEROP_WIRE=raw
cmake --build build-raw -j
ctest --test-dir build-raw --output-on-failure
```

In `protobuf` mode a generated model compiles its emitted `<Model>.proto` with
`protoc` into a `<model>_proto` static target and compiles `model_wire.cpp`.
That translation unit maps the typed signal members to and from the generated
`<Model>Payload` through the protobuf reflection API; the runtime never
hand-rolls protobuf bytes. It also exposes `encode_wire_frame` /
`decode_wire_frame`, which wrap the payload in the runtime envelope. In `raw`
mode `model_wire.cpp` is not compiled.

The generated project also builds `wire_conformance`, which prints the hex of
one frame encoded from the reset state. `tests/test_wire_conformance.py` builds
the same model, encodes the equivalent payload with the Python protobuf
runtime, and asserts the two frames are byte-identical, for example:

```text
50464d4901003000983f897eb99c8464
070000002a0000000000000000002a36fe9c9717
24000000a3cc6f06
df6a46d9
0a0909000000000000f83f1204220268691a021801220210042a09090000000000000000
```
