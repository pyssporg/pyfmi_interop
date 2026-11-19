# Wire envelope (v2)

`pyfmi_interop.wire` defines the framing around an opaque payload: a fixed
56-byte header, a payload, and two CRC32 checks. The payload schema and its
generated bindings are a separate contract; this module never parses the
payload and has no protobuf dependency.

* The layout is **little-endian** and packed with `struct` (`<`), so there is
  no padding and no alignment requirement.
* `HEADER_SIZE = 56` and `WIRE_VERSION = 2`.
* Encoding is deterministic: equal model, payload, `instance`, `sequence`,
  `timestamp_ns`, and payload format produce byte-identical frames.
* The codec never reads the clock. `sequence` and `timestamp_ns` are always
  caller-supplied.

## Transport boundary

A frame is transport-independent bytes. Byte transports (`loopback`, `udp`,
`tcp`) carry whole frames; see [Transport seam](#transport-seam). Discovery,
medium, and protocol semantics belong elsewhere and never change the envelope.

## Byte layout

All multi-byte integers are unsigned little-endian.

| Offset | Width | Field | Type / value |
| ---: | ---: | --- | --- |
| 0 | 4 | magic | ASCII `PFMI` (`b"PFMI"`) |
| 4 | 2 | wire version | uint16, `2` |
| 6 | 2 | header size | uint16, `56` |
| 8 | 8 | model id | 8 raw bytes, derived below |
| 16 | 4 | instance id | uint32 |
| 20 | 8 | sequence | uint64 |
| 28 | 8 | timestamp | uint64 nanoseconds |
| 36 | 4 | payload length | uint32, bytes |
| 40 | 4 | payload CRC32 | uint32 over payload bytes only |
| 44 | 2 | payload format | uint16: `0` opaque, `1` protobuf, `2` packed |
| 46 | 2 | flags | uint16, must be `0` |
| 48 | 4 | reserved | uint32, must be `0` |
| 52 | 4 | header CRC32 | uint32 over header bytes `0..51` |
| 56 | *n* | payload | bytes, `n` = payload length |

The header CRC field is the last header field, so it is never part of its own
input. The payload CRC is computed before the header and is carried as a normal
header field. `flags` and `reserved` are reserved for future versions and must
be zero; a v2 reader rejects any other value.

The equivalent Python packing is:

```python
header_prefix = struct.pack(
    "<4sHH8sIQQIIHHI",
    b"PFMI", 2, 56, model_id, instance, sequence, timestamp_ns,
    len(payload), payload_crc32, payload_format, 0, 0,
)
header_crc32 = zlib.crc32(header_prefix) & 0xFFFFFFFF
frame = header_prefix + struct.pack("<I", header_crc32) + payload
```

`decode` also rejects a buffer that holds more bytes than the declared frame
(`TrailingBytes`) so one buffer cannot silently contain two frames.

### Payload format

The envelope never interprets the payload, but it tags what the sender wrote so
the receiver can reject a mismatched serializer before parsing:

| Value | Name | Meaning |
| ---: | --- | --- |
| 0 | `opaque` | caller-defined bytes; the `raw` build |
| 1 | `protobuf` | a `<Model>Payload` protobuf message |
| 2 | `packed` | reserved for a future packed encoding |

The tag is exposed on the decoded frame (`DecodedFrame.header.payload_format`
in Python, `DecodedFrame.frame.header.payload_format` in C++) as an enum. Any
other value is `UnsupportedPayloadFormat`. Both encoders default to `0`
(opaque); a generated codec passes `1` (protobuf) or `2` (packed) explicitly.

### Rejection rules

A v2 decoder rejects, in this order:

1. a buffer shorter than 56 bytes (`TruncatedFrame`);
2. magic other than `PFMI` (`InvalidMagic`);
3. a wire version other than `2` (`UnsupportedWireVersion`);
4. a header size other than `56` (`InvalidHeaderSize`);
5. nonzero flags (`NonZeroFlags`) or reserved (`NonZeroReserved`);
6. a header CRC mismatch (`HeaderChecksumError`);
7. an unknown payload format (`UnsupportedPayloadFormat`);
8. a payload length that overflows uint32 or a frame shorter than declared
   (`LengthOverflow`);
9. trailing bytes (`TrailingBytes`);
10. a payload CRC mismatch (`PayloadChecksumError`).

Header and payload CRC failures have distinct errors; `ChecksumError` remains
the shared parent.

### Compatibility with v1 readers

The layout is intentionally incompatible. A v1 reader sees wire version `2`
at offset 4 and raises `UnsupportedWireVersion`; it never misreads a v2 frame
as v1. A v2 reader likewise rejects a v1 frame (`wire version 1 is not
supported (expected 2)`). There is no dual-version decoder: both ends must be
upgraded together. `model_id` derivation is unchanged, so an interface
identity is comparable across the version bump.

## Model id derivation

`model_id(model)` returns the first 8 bytes of SHA-256 over this exact byte
sequence (the domain separator keeps its v1 name and value):

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
* **Header CRC32** covers header bytes `0..51` inclusive (magic through
  reserved), excluding itself and the payload.

## Error taxonomy

All derive from `WireError`; `decode` never raises a bare `struct.error`.

| Exception | Raised when |
| --- | --- |
| `WireError` | base class for every envelope failure |
| `InvalidMagic` | bytes `0..3` are not `PFMI` |
| `UnsupportedWireVersion` | wire version is not `2` |
| `InvalidHeaderSize` | header size is not `56` |
| `UnsupportedPayloadFormat` | payload format is not 0, 1, or 2 |
| `NonZeroFlags` | the flags field is not zero |
| `NonZeroReserved` | the reserved field is not zero |
| `TruncatedFrame` | buffer is shorter than the fixed 56-byte header |
| `LengthOverflow` | declared payload length overflows uint32, or the declared frame extends past the buffer |
| `TrailingBytes` | buffer holds more bytes than the declared frame |
| `ChecksumError` | base class for CRC failures |
| `HeaderChecksumError` | header CRC32 mismatch |
| `PayloadChecksumError` | payload CRC32 mismatch |
| `FieldRangeError` | an `encode` argument does not fit its field |

## Worked example

Model `demo`, step size `0.01`, signals `alpha` (id 1, real/output) and `beta`
(id 2, integer/input). Instance 7, sequence 42, timestamp
`1_700_000_000_000_000_000` ns, payload format opaque (the encoder default), payload `b"hello"`:

```
50464d49 0200 3800 ee78acea761957f0
07000000 2a00000000000000 00002a36fe9c9717
05000000 86a61036 0000 0000 00000000 c2b06e48
68656c6c6f
```

| Bytes | Field | Value |
| --- | --- | --- |
| `50464d49` | magic | `PFMI` |
| `0200` | wire version | 2 |
| `3800` | header size | 56 (0x38) |
| `ee78acea761957f0` | model id | derived, see above |
| `07000000` | instance | 7 |
| `2a00000000000000` | sequence | 42 |
| `00002a36fe9c9717` | timestamp | 1 700 000 000 000 000 000 ns |
| `05000000` | payload length | 5 |
| `86a61036` | payload CRC32 | `zlib.crc32(b"hello")` |
| `0000` | payload format | opaque |
| `0000` | flags | 0 |
| `00000000` | reserved | 0 |
| `c2b06e48` | header CRC32 | over bytes `0..51` |
| `68656c6c6f` | payload | `hello` |

Empty payload for the same model and header values (format opaque):

```
50464d4902003800ee78acea761957f0070000002a0000000000000000002a36fe9c971700000000000000000000000000000000006fef80de
```

## Transport seam

The runtime ships a byte-frame `Transport` interface, a static registry, and
three backends. All calls are non-blocking; the step loop never waits for a
peer.

### Interface

```cpp
class Transport {
public:
    virtual void initialize(const std::string& uri);
    virtual void finalize();
    virtual bool send(std::span<const std::byte> frame) = 0;
    virtual std::optional<std::vector<std::byte>> receive() = 0;
    virtual TransportStats stats() const;
};
```

`send` returns false when the frame could not be accepted (the socket would
block, or no peer is known yet); the caller skips the frame. `receive` returns
the newest queued frame, discards older ones, and counts them as
`dropped_stale`; it never queues unboundedly. A backend that cannot honour its
configuration throws `TransportError` from `initialize`.

### URI grammar

Configuration is parsed in one place (`transport/src/transport_uri.cpp`):

```
loopback
udp://<bind-host>:<port>[?peer=<host>:<port>]
tcp://<bind-host>:<port>[?peer=<host>:<port>]
```

* `<port>` is decimal; `0` asks the OS for an ephemeral port.
* UDP: one datagram is one frame. Frames larger than 65507 bytes are rejected
  with `TransportError`; `SO_RCVBUF` is maximized and receive drains to the
  newest datagram. Without `peer=`, the backend sends to the last observed
  sender.
* TCP: without `peer=` the backend listens and accepts one peer; with `peer=`
  it connects. The envelope is self-delimiting, so partial reads are buffered
  until the 56-byte header yields `payload_length` and the whole frame is
  present. A peer disconnect closes that connection without blocking the step.
* IPv6 literals use brackets (`[::1]:port`); the POSIX reference backend
  currently implements IPv4 sockets.

`PYFMI_INTEROP_TRANSPORT` carries the URI. An empty value selects `loopback`;
`none` disables the transport. The legacy
`PYFMI_INTEROP_TRANSPORT_ENDPOINT` still supplies the authority when the value
is a bare scheme. A model whose role is `none` never opens a transport.

### Registry

Backends register from static initializers:

```cpp
REGISTER_TRANSPORT("loopback", []() -> std::unique_ptr<Transport> {
    return std::make_unique<LoopbackTransport>();
});
```

`make_transport(name_or_uri)` selects by scheme (`loopback`, `udp`, `tcp`) and
throws `TransportError` listing every registered name when the scheme is
unknown. `transport_names()` returns the sorted names. The UDP and TCP
backends live in the static library `pyfmi_interop_transport`, so consumers
link that archive with whole-archive to keep its registration objects.

### Stats

| Counter | Meaning |
| --- | --- |
| `frames_sent` | frames fully handed to the OS |
| `frames_received` | frames returned by `receive()` |
| `crc_errors` | frames dropped for a header or payload CRC failure |
| `format_errors` | frames dropped for an unknown tag, a serializer mismatch, or a bad payload |
| `model_id_mismatches` | frames dropped because the model id does not match |
| `dropped_stale` | older queued frames discarded in favour of a newer one |

The byte backends own the queue counters. `crc_errors`, `format_errors`, and
`model_id_mismatches` are recorded by the consumer (the FMI facade) after it
validates a received envelope; `record_crc_error()`, `record_format_error()`,
and `record_model_id_mismatch()` update them without changing the ABI.

### Roles and serialization

The generated model reports its role and codec through the optional
`WireModelCodec` interface (`runtime/include/pyfmi_interop/runtime/model_runtime.hpp`):

```cpp
enum class TransportRole { None, Sender, Receiver, Adapter };

class WireModelCodec {
    virtual TransportRole transport_role() const = 0;
    virtual wire::PayloadFormat payload_format() const = 0;
    virtual bool wire_model_id(std::array<std::uint8_t, 8>& out) const = 0;
    virtual bool encode_wire_payload(std::string&, std::string&) const = 0;
    virtual bool decode_wire_payload(std::string_view, std::string&) = 0;
};
```

`ModelRuntime::wire_codec()` returns the codec (the generated model returns
`this`); a model that returns `nullptr` keeps the historical step-only path.
The serialization selection is the existing compile-time wire mode:
`PYFMI_INTEROP_WIRE_PROTOBUF` selects `payload_format = 1`, the `raw` build
selects `0`, and `wire::payload_mode_name()` exposes the choice. No new
environment variable selects the serializer.

`fmi2DoStep` then runs:

| Role | Order |
| --- | --- |
| `none` | step only (exactly the pre-transport behaviour) |
| `sender` | step → encode output values → frame → send (skipped if it would block) |
| `receiver` | receive newest → validate model id and payload format → apply input values → step; no frame holds the previous values and increments an internal miss counter |
| `adapter` | receive → apply → step → publish → send |

A frame with a bad CRC, a mismatched model id, a mismatched serializer, or a
payload the codec rejects is dropped and counted; the step continues with the
previous input values rather than failing or injecting NaN.

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
`<4sHH8sIQQIIHHI` field order and widths, little-endian integers, `crc32` with
the reflected IEEE 802.3 polynomial and init/xorout `0xFFFFFFFF`, the same
model-id domain separator and `<d`/`<IB` record layout, magic `PFMI`, version
`2`, and header size `56`. The CRC over `"123456789"` is `0xCBF43926`.

### Runtime files

| File | Purpose |
| --- | --- |
| `runtime/include/pyfmi_interop/runtime/wire.hpp` | `encode_frame` / `decode_frame`, `Header`, `Frame`, `PayloadFormat`, `ErrorCode` / `WireError`, `crc32`, `sha256`, `model_id` |
| `runtime/src/wire.cpp` | Packed little-endian envelope, CRC32/ISO-HDLC table, portable SHA-256 (no OpenSSL) |
| `runtime/include/pyfmi_interop/runtime/transport.hpp` | Byte-frame `Transport`, `TransportStats`, registry, `REGISTER_TRANSPORT` |
| `runtime/include/pyfmi_interop/runtime/loopback_transport.hpp` | In-process reference byte transport |
| `transport/include/pyfmi_interop/transport/transport_uri.hpp` | URI grammar shared by the UDP and TCP backends |
| `transport/include/pyfmi_interop/transport/udp_transport.hpp` | One-datagram-per-frame UDP backend |
| `transport/include/pyfmi_interop/transport/tcp_transport.hpp` | Stream backend with envelope reassembly |
| `runtime/include/pyfmi_interop/runtime/payload.hpp` | `PayloadCodec` interface plus the compile-time `payload_mode_name()` |
| `runtime/src/payload.cpp` | Reports the selected payload mode to dependents |

`ErrorCode` names mirror the Python taxonomy: `InvalidMagic`,
`UnsupportedWireVersion`, `InvalidHeaderSize`, `UnsupportedPayloadFormat`,
`NonZeroFlags`, `NonZeroReserved`, `TruncatedFrame`, `LengthOverflow`,
`TrailingBytes`, `HeaderChecksumError`, `PayloadChecksumError`, and
`FieldRangeError`, with `ChecksumError` as the shared CRC parent.
`encode_frame`/`decode_frame` return a result carrying the frame and a
`WireError`; they never throw. Decode checks in the same order as Python:
truncation, magic, version, header size, payload format, flags/reserved, header
CRC32, declared length, trailing bytes, payload CRC32.

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
payload-agnostic: caller bytes are carried unchanged with payload format `0`.

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
50464d4902003800983f897eb99c8464
070000002a0000000000000000002a36fe9c9717
24000000a3cc6f060100000000000000
0aebb9cb
0a0909000000000000f83f1204220268691a021801220210042a09090000000000000000
```
