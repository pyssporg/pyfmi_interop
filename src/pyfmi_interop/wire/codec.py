"""Versioned, CRC-protected envelope around an opaque protobuf payload.

The envelope is little-endian and packed with :mod:`struct` (standard sizes,
no padding, no alignment requirement).  The payload is opaque bytes: this
module never parses it and has no protobuf dependency.

Encoding is deterministic: equal model, payload, instance, sequence, and
timestamp produce byte-identical frames.  The codec never reads the clock;
``sequence`` and ``timestamp_ns`` are always caller-supplied.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Any

from ..ir import ModelDefinition
from .errors import (
    FieldRangeError,
    HeaderChecksumError,
    InvalidHeaderSize,
    InvalidMagic,
    LengthOverflow,
    PayloadChecksumError,
    TrailingBytes,
    TruncatedFrame,
    UnsupportedWireVersion,
)

__all__ = [
    "DecodedFrame",
    "HEADER_SIZE",
    "Header",
    "MODEL_ID_SIZE",
    "WIRE_MAGIC",
    "WIRE_VERSION",
    "decode",
    "encode",
    "model_id",
]

#: ASCII magic at offset 0: "PyFmi Interop".
WIRE_MAGIC = b"PFMI"

#: Envelope format version.  Bump only with an incompatible layout change.
WIRE_VERSION = 1

#: Length of the derived model id.
MODEL_ID_SIZE = 8

#: Header fields before the header CRC: magic, version, header size, model id,
#: instance, sequence, timestamp, payload length, payload CRC.
_PREFIX = struct.Struct("<4sHH8sIQQII")
#: The trailing header CRC32 field.
_U32 = struct.Struct("<I")

#: Fixed total header size in bytes.
HEADER_SIZE = _PREFIX.size + _U32.size
#: Offset of the header CRC32 field; the CRC covers ``0 .. HEADER_CRC_OFFSET``.
HEADER_CRC_OFFSET = _PREFIX.size

assert HEADER_SIZE == 48

#: Domain separator for :func:`model_id`; changing it changes every id.
_MODEL_ID_DOMAIN = b"pyfmi_interop.model-id.v1\x00"


@dataclass(frozen=True)
class Header:
    """Decoded envelope header.

    ``model_id`` is the derived interface identity, ``instance`` identifies one
    running instance, ``sequence`` orders frames from that instance, and
    ``timestamp_ns`` is the caller's nanosecond timestamp.  The CRC fields are
    carried so a decoded frame can be re-encoded or audited without guessing.
    """

    magic: bytes
    wire_version: int
    header_size: int
    model_id: bytes
    instance: int
    sequence: int
    timestamp_ns: int
    payload_length: int
    payload_crc32: int
    header_crc32: int


@dataclass(frozen=True)
class DecodedFrame:
    """A validated header and its payload bytes."""

    header: Header
    payload: bytes


def model_id(model: ModelDefinition) -> bytes:
    """Derive the 8-byte interface identity of ``model``.

    The digest input is, in order:

    * the domain separator ``b"pyfmi_interop.model-id.v1\\x00"``;
    * ``model.name`` encoded as UTF-8 followed by one NUL byte;
    * ``model.step_size_s`` as an IEEE 754 double, little-endian (``<d``);
    * one ``<IB`` record per signal, ordered by ``(value_reference, name)``:
      the value reference as uint32 followed by ``DataType.number`` as uint8.

    The result is the first 8 bytes of the SHA-256 digest.
    """

    digest = hashlib.sha256()
    digest.update(_MODEL_ID_DOMAIN)
    digest.update(model.name.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(struct.pack("<d", model.step_size_s))
    for signal in sorted(model.signals, key=lambda item: (item.value_reference, item.name)):
        digest.update(struct.pack("<IB", signal.value_reference, signal.data_type.number))
    return digest.digest()[:MODEL_ID_SIZE]


def encode(
    model: ModelDefinition,
    payload: bytes | bytearray | memoryview,
    *,
    instance: int,
    sequence: int,
    timestamp_ns: int,
) -> bytes:
    """Wrap ``payload`` in a header and return the complete frame.

    ``instance`` must fit uint32; ``sequence`` and ``timestamp_ns`` must fit
    uint64, and the payload must fit uint32.  Out-of-range values raise
    :class:`~.FieldRangeError` or :class:`~.LengthOverflow`; the codec does not
    truncate.  The timestamp is used verbatim and never read from the clock.
    """

    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    body = bytes(payload)
    _require_uint(instance, 32, "instance")
    _require_uint(sequence, 64, "sequence")
    _require_uint(timestamp_ns, 64, "timestamp_ns")
    if len(body) > 0xFFFFFFFF:
        raise LengthOverflow(f"payload is {len(body)} bytes, exceeding uint32 length")
    if HEADER_SIZE + len(body) > 0xFFFFFFFF:
        raise LengthOverflow("payload length plus header size exceeds uint32")

    payload_crc32 = zlib.crc32(body) & 0xFFFFFFFF
    prefix = _PREFIX.pack(
        WIRE_MAGIC,
        WIRE_VERSION,
        HEADER_SIZE,
        model_id(model),
        instance,
        sequence,
        timestamp_ns,
        len(body),
        payload_crc32,
    )
    header_crc32 = zlib.crc32(prefix) & 0xFFFFFFFF
    return prefix + _U32.pack(header_crc32) + body


def decode(buf: bytes | bytearray | memoryview) -> DecodedFrame:
    """Validate ``buf`` as one frame and return its header and payload.

    Checks, in order: fixed-header truncation, magic, wire version, header
    size, header CRC32, declared length, trailing bytes, payload CRC32.  Every
    failure is a :class:`~.WireError` subclass; a ``struct.error`` never
    escapes.
    """

    if not isinstance(buf, (bytes, bytearray, memoryview)):
        raise TypeError("buf must be bytes-like")
    view = memoryview(buf)
    if view.format != "B":
        view = view.cast("B")
    if len(view) < HEADER_SIZE:
        raise TruncatedFrame(
            f"buffer holds {len(view)} bytes, shorter than the {HEADER_SIZE}-byte header"
        )

    try:
        prefix = _PREFIX.unpack_from(view, 0)
        (header_crc32,) = _U32.unpack_from(view, HEADER_CRC_OFFSET)
    except struct.error as exc:  # defensive: length was checked above
        raise TruncatedFrame("buffer is too short to contain a header") from exc

    (
        magic,
        wire_version,
        header_size,
        raw_model_id,
        instance,
        sequence,
        timestamp_ns,
        payload_length,
        payload_crc32,
    ) = prefix

    if magic != WIRE_MAGIC:
        raise InvalidMagic(f"bad magic {bytes(magic)!r}")
    if wire_version != WIRE_VERSION:
        raise UnsupportedWireVersion(
            f"wire version {wire_version} is not supported (expected {WIRE_VERSION})"
        )
    if header_size != HEADER_SIZE:
        raise InvalidHeaderSize(
            f"header size {header_size} does not match {HEADER_SIZE}"
        )
    actual_header_crc32 = zlib.crc32(view[:HEADER_CRC_OFFSET]) & 0xFFFFFFFF
    if actual_header_crc32 != header_crc32:
        raise HeaderChecksumError(
            f"header CRC32 {header_crc32:#010x} != {actual_header_crc32:#010x}"
        )

    if payload_length > 0xFFFFFFFF - HEADER_SIZE:
        raise LengthOverflow(
            f"payload length {payload_length} overflows the uint32 frame length"
        )
    total = HEADER_SIZE + payload_length
    if total > len(view):
        raise LengthOverflow(
            f"frame declares {total} bytes but the buffer holds {len(view)}"
        )
    if total < len(view):
        raise TrailingBytes(f"frame is {total} bytes but the buffer holds {len(view)}")

    payload = bytes(view[HEADER_SIZE:total])
    actual_payload_crc32 = zlib.crc32(payload) & 0xFFFFFFFF
    if actual_payload_crc32 != payload_crc32:
        raise PayloadChecksumError(
            f"payload CRC32 {payload_crc32:#010x} != {actual_payload_crc32:#010x}"
        )

    header = Header(
        magic=bytes(magic),
        wire_version=wire_version,
        header_size=header_size,
        model_id=bytes(raw_model_id),
        instance=instance,
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        payload_length=payload_length,
        payload_crc32=payload_crc32,
        header_crc32=header_crc32,
    )
    return DecodedFrame(header=header, payload=payload)


def _require_uint(value: Any, bits: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldRangeError(f"{name} must be an integer")
    if not 0 <= value <= (1 << bits) - 1:
        raise FieldRangeError(f"{name} {value} does not fit uint{bits}")
