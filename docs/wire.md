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

## C++ end (W6)

To match Python byte for byte, the C++ implementation must use the same
`<4sHH8sIQQII` field order and widths, little-endian integers, `crc32` with the
reflected IEEE 802.3 polynomial and init/xorout `0xFFFFFFFF`, the same model-id
domain separator and `<d`/`<IB` record layout, magic `PFMI`, version `1`, and
header size `48`. The CRC over `"123456789"` must be `0xCBF43926`.
