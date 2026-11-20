"""Envelope contract: v2 layout, CRCs, golden frames, and the error taxonomy."""

from __future__ import annotations

import struct
import zlib

import pytest

from pyfmi_interop import ir, wire

pytestmark = pytest.mark.unit

_PREFIX = struct.Struct("<4sHH8sIQQIIHHI")

#: model name "demo", signals alpha(1, real/out), beta(2, integer/in).
MODEL_ID_HEX = "d6b64a33d05b491b"

# Empty payload, opaque format (0), instance 7, sequence 42,
# timestamp 1_700_000_000_000_000_000 ns.
EMPTY_FRAME_HEX = (
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "00000000000000000000000000000000"
    "ce540190"
)
# Same header, payload b"hello".
HELLO_FRAME_HEX = (
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "0500000086a610360000000000000000"
    "630bef06"
    "68656c6c6f"
)
# Same header, payload bytes(range(256)): the uint8 length boundary.
BOUNDARY_FRAME_HEX = (
    "50464d4902003800d6b64a33d05b491b"
    "070000002a0000000000000000002a36fe9c9717"
    "00010000738c05290000000000000000"
    "c684aecf"
) + bytes(range(256)).hex()


def _model() -> ir.ModelDefinition:
    return ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.01,
        signals=(
            ir.Signal("alpha", 1, ir.DataType.REAL, ir.Direction.OUTPUT),
            ir.Signal("beta", 2, ir.DataType.INTEGER, ir.Direction.INPUT),
        ),
    )


def _frame(
    payload: bytes = b"hello",
    payload_format: int | wire.PayloadFormat = wire.PayloadFormat.OPAQUE,
) -> bytes:
    return wire.encode(
        _model(),
        payload,
        instance=7,
        sequence=42,
        timestamp_ns=1_700_000_000_000_000_000,
        payload_format=payload_format,
    )


def _with_header(frame: bytes, **changes: object) -> bytes:
    """Rebuild the header with valid CRCs, for header-field error cases."""

    names = (
        "magic",
        "wire_version",
        "header_size",
        "model_id",
        "instance",
        "sequence",
        "timestamp_ns",
        "payload_length",
        "payload_crc32",
        "payload_format",
        "flags",
        "reserved",
    )
    fields = dict(zip(names, _PREFIX.unpack_from(frame, 0), strict=True))
    fields.update(changes)
    prefix = _PREFIX.pack(*fields.values())
    return (
        prefix
        + struct.pack("<I", zlib.crc32(prefix) & 0xFFFFFFFF)
        + frame[wire.HEADER_SIZE :]
    )


def test_public_api_is_exported_from_the_package_root() -> None:
    import pyfmi_interop

    for name in (
        "HEADER_SIZE",
        "WIRE_VERSION",
        "Header",
        "DecodedFrame",
        "PayloadFormat",
        "WireError",
        "NonZeroFlags",
        "NonZeroReserved",
        "UnsupportedPayloadFormat",
    ):
        assert hasattr(pyfmi_interop, name)


def test_header_size_and_version_are_frozen() -> None:
    assert wire.HEADER_SIZE == 56
    assert wire.WIRE_VERSION == 2
    assert wire.WIRE_MAGIC == b"PFMI"
    assert [int(member) for member in wire.PayloadFormat] == [0, 1, 2]


def test_crc32_is_ieee_802_3() -> None:
    assert zlib.crc32(b"123456789") == 0xCBF43926


def test_model_id_is_stable() -> None:
    assert wire.model_id(_model()).hex() == MODEL_ID_HEX


def test_model_id_ignores_step_size_but_changes_with_the_interface() -> None:
    base = wire.model_id(_model())
    stepped = ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.02,
        signals=_model().signals,
    )
    rated = ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.01,
        signals=(
            ir.Signal("alpha", 1, ir.DataType.REAL, ir.Direction.OUTPUT, rate_hz=10.0),
            _model().signals[1],
        ),
    )
    retyped = ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.01,
        signals=(_model().signals[0],),
    )
    assert wire.model_id(stepped) == base
    assert wire.model_id(rated) == base
    assert wire.model_id(retyped) != base


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", EMPTY_FRAME_HEX),
        (b"hello", HELLO_FRAME_HEX),
        (bytes(range(256)), BOUNDARY_FRAME_HEX),
    ],
    ids=["empty", "small", "uint8-boundary"],
)
def test_golden_frames(payload: bytes, expected: str) -> None:
    assert _frame(payload).hex() == expected


def test_payload_format_is_tagged_in_the_header() -> None:
    for member in wire.PayloadFormat:
        decoded = wire.decode(_frame(b"hello", member))
        assert decoded.header.payload_format == int(member)


def test_encoding_is_deterministic() -> None:
    assert _frame() == _frame()


def test_round_trip_preserves_header_and_payload() -> None:
    frame = _frame()
    decoded = wire.decode(frame)

    assert isinstance(decoded, wire.DecodedFrame)
    assert isinstance(decoded.header, wire.Header)
    assert decoded.payload == b"hello"
    assert decoded.header.magic == b"PFMI"
    assert decoded.header.wire_version == 2
    assert decoded.header.header_size == 56
    assert decoded.header.model_id.hex() == MODEL_ID_HEX
    assert decoded.header.instance == 7
    assert decoded.header.sequence == 42
    assert decoded.header.timestamp_ns == 1_700_000_000_000_000_000
    assert decoded.header.payload_length == 5
    assert decoded.header.payload_crc32 == zlib.crc32(b"hello") & 0xFFFFFFFF
    assert decoded.header.payload_format == int(wire.PayloadFormat.OPAQUE)
    assert decoded.header.flags == 0
    assert decoded.header.reserved == 0
    # Re-encoding a decoded frame is byte-identical.
    assert (
        wire.encode(
            _model(),
            decoded.payload,
            instance=decoded.header.instance,
            sequence=decoded.header.sequence,
            timestamp_ns=decoded.header.timestamp_ns,
            payload_format=decoded.header.payload_format,
        )
        == frame
    )


def test_sequence_and_timestamp_are_caller_supplied() -> None:
    first = wire.encode(_model(), b"", instance=1, sequence=1, timestamp_ns=10)
    second = wire.encode(_model(), b"", instance=1, sequence=2, timestamp_ns=11)
    assert wire.decode(first).header.timestamp_ns == 10
    assert wire.decode(second).header.sequence == 2
    assert first != second


def test_decoder_accepts_bytearray_and_memoryview() -> None:
    frame = _frame()
    assert wire.decode(bytearray(frame)).payload == b"hello"
    assert wire.decode(memoryview(frame)).payload == b"hello"


def test_bad_magic() -> None:
    with pytest.raises(wire.InvalidMagic):
        wire.decode(_with_header(_frame(), magic=b"XXXX"))


def test_unknown_wire_version() -> None:
    # Version 1 is the previous layout and is no longer accepted.
    with pytest.raises(wire.UnsupportedWireVersion):
        wire.decode(_with_header(_frame(), wire_version=1))


def test_bad_header_size() -> None:
    with pytest.raises(wire.InvalidHeaderSize):
        wire.decode(_with_header(_frame(), header_size=48))


def test_nonzero_flags_are_rejected() -> None:
    with pytest.raises(wire.InvalidFlags):
        wire.decode(_with_header(_frame(), flags=1))
    assert wire.NonZeroFlags is wire.InvalidFlags


def test_nonzero_reserved_is_rejected() -> None:
    with pytest.raises(wire.InvalidReserved):
        wire.decode(_with_header(_frame(), reserved=1))
    assert wire.NonZeroReserved is wire.InvalidReserved


def test_unsupported_payload_format_is_rejected() -> None:
    with pytest.raises(wire.UnsupportedPayloadFormat):
        wire.decode(_with_header(_frame(), payload_format=99))


def test_encode_rejects_an_unsupported_payload_format() -> None:
    with pytest.raises(wire.FieldRangeError, match="payload_format"):
        _frame(b"", 99)


def test_bad_header_crc() -> None:
    frame = bytearray(_frame())
    frame[55] ^= 0x01
    with pytest.raises(wire.HeaderChecksumError):
        wire.decode(frame)


def test_bad_payload_crc() -> None:
    frame = bytearray(_frame())
    frame[-1] ^= 0x01
    with pytest.raises(wire.PayloadChecksumError):
        wire.decode(frame)


@pytest.mark.parametrize("length", [0, 1, 55])
def test_truncated_header(length: int) -> None:
    with pytest.raises(wire.TruncatedFrame):
        wire.decode(_frame()[:length])


def test_payload_shorter_than_declared_is_length_overflow() -> None:
    with pytest.raises(wire.LengthOverflow):
        wire.decode(_frame()[:-1])


def test_declared_length_beyond_uint32_is_length_overflow() -> None:
    with pytest.raises(wire.LengthOverflow):
        wire.decode(_with_header(_frame(), payload_length=0xFFFFFFFF))


def test_trailing_bytes_are_rejected() -> None:
    with pytest.raises(wire.TrailingBytes):
        wire.decode(_frame() + b"\x00")


def test_truncated_and_overflow_errors_are_wire_errors() -> None:
    assert issubclass(wire.TruncatedFrame, wire.WireError)
    assert issubclass(wire.LengthOverflow, wire.WireError)
    assert issubclass(wire.HeaderChecksumError, wire.ChecksumError)
    assert issubclass(wire.PayloadChecksumError, wire.ChecksumError)
    assert issubclass(wire.ChecksumError, wire.WireError)
    assert issubclass(wire.InvalidFlags, wire.WireError)
    assert issubclass(wire.InvalidReserved, wire.WireError)
    assert issubclass(wire.UnsupportedPayloadFormat, wire.WireError)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"instance": 2**32}, "instance"),
        ({"sequence": 2**64}, "sequence"),
        ({"timestamp_ns": -1}, "timestamp_ns"),
        ({"instance": True}, "instance"),
    ],
)
def test_encode_rejects_out_of_range_fields(kwargs: dict, message: str) -> None:
    values = {"instance": 0, "sequence": 0, "timestamp_ns": 0}
    values.update(kwargs)
    with pytest.raises(wire.FieldRangeError, match=message):
        wire.encode(_model(), b"", **values)


def test_encode_rejects_non_bytes_payload() -> None:
    with pytest.raises(TypeError):
        wire.encode(_model(), "hello", instance=0, sequence=0, timestamp_ns=0)  # type: ignore[arg-type]


def test_every_single_bit_flip_is_detected() -> None:
    """The header CRC32 covers bytes 0..51; the payload CRC32 covers the payload.

    A flip in magic, version, header size, flags, reserved, or format is caught
    by the typed field check before or after the CRC; every other header flip by
    the header CRC.  Every payload flip is caught by the payload CRC.
    """

    frame = bytearray(_frame())
    for index in range(wire.HEADER_SIZE):
        for bit in range(8):
            mutated = bytearray(frame)
            mutated[index] ^= 1 << bit
            with pytest.raises(wire.WireError):
                wire.decode(mutated)

    payload_offset = wire.HEADER_SIZE
    for index in range(payload_offset, len(frame)):
        for bit in range(8):
            mutated = bytearray(frame)
            mutated[index] ^= 1 << bit
            with pytest.raises(wire.PayloadChecksumError):
                wire.decode(mutated)
