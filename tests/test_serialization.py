"""Serialization registry, packed encoding, and format tagging."""

from __future__ import annotations

import struct

import pytest

from pyfmi_interop import ir, wire
from pyfmi_interop.serialization import get, names, opaque, packed, protobuf, register
from pyfmi_interop.serialization.base import Serialization

pytestmark = pytest.mark.unit


def _model() -> ir.ModelDefinition:
    return ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.01,
        signals=(
            ir.Signal("alpha", 1, ir.DataType.REAL, ir.Direction.OUTPUT),
            ir.Signal("beta", 2, ir.DataType.INTEGER, ir.Direction.INPUT),
            ir.Signal("flag", 3, ir.DataType.BOOLEAN, ir.Direction.PARAMETER),
            ir.Signal("label", 4, ir.DataType.STRING, ir.Direction.OUTPUT, capacity=8),
        ),
    )


def test_registry_lists_the_three_backends():
    assert names() == ("protobuf", "packed", "opaque")
    assert get("protobuf") is protobuf.backend
    assert get("packed") is packed.backend
    assert get("opaque") is opaque.backend


def test_unknown_backend_is_an_error():
    with pytest.raises(KeyError, match="unknown serialization backend"):
        get("nope")


def test_duplicate_registration_is_an_error():
    class Duplicate(Serialization):
        name = "packed"
        format_id = 2

        def schema_files(self, model):
            return {}

        def generate_codec(self, model, out, role):
            return []

    with pytest.raises(ValueError, match="already registered"):
        register(Duplicate())


def test_format_ids_are_stable():
    assert (protobuf.backend.name, protobuf.backend.format_id) == ("protobuf", 1)
    assert (packed.backend.name, packed.backend.format_id) == ("packed", 2)
    assert (opaque.backend.name, opaque.backend.format_id) == ("opaque", 0)


def test_packed_round_trip():
    model = _model()
    values = {"alpha": 1.5, "beta": -7, "flag": True, "label": "hi"}

    payload = packed.encode(model, values)

    assert packed.decode(model, payload) == {
        "alpha": 1.5,
        "beta": -7,
        "flag": True,
        "label": "hi",
    }


def test_packed_layout_is_little_endian_and_field_ordered():
    model = _model()
    payload = packed.encode(
        model, {"alpha": 1.0, "beta": 2, "flag": True, "label": "A"}
    )

    # alpha <d>, beta <i, flag <B, label <I length + bytes.
    assert payload == (
        struct.pack("<d", 1.0)
        + struct.pack("<i", 2)
        + struct.pack("<B", 1)
        + struct.pack("<I", 1)
        + b"A"
    )


def test_packed_is_byte_identical_across_runs():
    model = _model()
    values = {"alpha": 1.5, "beta": -7, "flag": False, "label": "stable"}

    first = packed.encode(model, values)
    second = packed.encode(model, values)
    third = packed.encode(model, dict(reversed(list(values.items()))))

    assert first == second == third


def test_packed_uses_initial_values_for_missing_fields():
    model = _model()
    payload = packed.encode(model, {})

    assert packed.decode(model, payload) == {
        "alpha": 0.0,
        "beta": 0,
        "flag": False,
        "label": "",
    }


def test_packed_rejects_a_truncated_payload():
    model = _model()
    payload = packed.encode(model, {"label": "hi"})
    with pytest.raises(ValueError, match="truncated|inside"):
        packed.decode(model, payload[:-1])


def test_packed_rejects_trailing_bytes():
    model = _model()
    payload = packed.encode(model, {})
    with pytest.raises(ValueError, match="trailing"):
        packed.decode(model, payload + b"\x00")


def test_packed_rejects_a_string_over_capacity():
    model = _model()
    with pytest.raises(ir.ProjectionError, match="capacity"):
        packed.encode(model, {"label": "too long!"})


def test_opaque_is_a_passthrough():
    assert opaque.encode(b"\x00\x01raw") == b"\x00\x01raw"
    assert opaque.decode(memoryview(b"raw")) == b"raw"
    with pytest.raises(TypeError):
        opaque.encode("not bytes")  # type: ignore[arg-type]


def test_payload_format_rejects_a_backend_mismatch_at_the_framing_layer():
    model = _model()
    protobuf_frame = wire.encode(
        model,
        b"payload",
        instance=1,
        sequence=1,
        timestamp_ns=1,
        payload_format=wire.PayloadFormat.PROTOBUF,
    )
    packed_frame = wire.encode(
        model,
        b"payload",
        instance=1,
        sequence=1,
        timestamp_ns=1,
        payload_format=wire.PayloadFormat.PACKED,
    )

    assert wire.decode(protobuf_frame).header.payload_format == 1
    assert wire.decode(packed_frame).header.payload_format == 2
    # A decoder can compare the tag before handing the bytes to a codec.
    assert wire.decode(packed_frame).payload == wire.decode(protobuf_frame).payload
    with pytest.raises(wire.UnsupportedPayloadFormat):
        wire.decode(_retag(protobuf_frame, 7))


def _retag(frame: bytes, payload_format: int) -> bytes:
    import zlib

    prefix = struct.Struct("<4sHH8sIQQIIHHI")
    fields = list(prefix.unpack_from(frame, 0))
    fields[9] = payload_format
    rebuilt = prefix.pack(*fields)
    return (
        rebuilt
        + struct.pack("<I", zlib.crc32(rebuilt) & 0xFFFFFFFF)
        + frame[wire.HEADER_SIZE :]
    )
