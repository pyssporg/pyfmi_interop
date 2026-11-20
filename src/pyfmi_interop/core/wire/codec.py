"""Versioned, CRC-protected envelope around a payload.

Wire version 2 fixes a 56-byte little-endian header and adds an explicit
``payload_format`` tag so a decoder can tell opaque bytes (``0``), a protobuf
payload (``1``), and a packed payload (``2``) apart.  The envelope is packed
with :mod:`struct` (standard sizes, no padding, no alignment requirement) and
never parses the payload.

Encoding is deterministic: equal model, payload, instance, sequence, format,
and timestamp produce byte-identical frames.  The codec never reads the clock;
``sequence`` and ``timestamp_ns`` are always caller-supplied.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..ir import Direction, ModelDefinition
from .errors import (
    FieldRangeError,
    HeaderChecksumError,
    InvalidFlags,
    InvalidHeaderSize,
    InvalidMagic,
    InvalidReserved,
    LengthOverflow,
    PayloadChecksumError,
    TrailingBytes,
    TruncatedFrame,
    UnsupportedPayloadFormat,
    UnsupportedWireVersion,
)

__all__ = [
    "DecodedFrame",
    "HEADER_SIZE",
    "Header",
    "MODEL_ID_SIZE",
    "PayloadFormat",
    "WIRE_MAGIC",
    "WIRE_VERSION",
    "decode",
    "encode",
    "model_id",
]

#: ASCII magic at offset 0: "PyFmi Interop".
WIRE_MAGIC = b"PFMI"

#: Envelope format version.  Bump only with an incompatible layout change.
WIRE_VERSION = 2

#: Length of the derived model id.
MODEL_ID_SIZE = 8


class PayloadFormat(IntEnum):
    """Values of the 16-bit ``payload_format`` header field."""

    OPAQUE = 0
    PROTOBUF = 1
    PACKED = 2


#: Header fields before the header CRC: magic, version, header size, model id,
#: instance, sequence, timestamp, payload length, payload CRC, payload format,
#: flags, reserved.
_PREFIX = struct.Struct("<4sHH8sIQQIIHHI")
#: The trailing header CRC32 field.
_U32 = struct.Struct("<I")

#: Fixed total header size in bytes.
HEADER_SIZE = _PREFIX.size + _U32.size
#: Offset of the header CRC32 field; the CRC covers ``0 .. HEADER_CRC_OFFSET``.
HEADER_CRC_OFFSET = _PREFIX.size

assert HEADER_SIZE == 56
assert HEADER_CRC_OFFSET == 52

#: Domain separator for :func:`model_id`; changing it changes every id.
_MODEL_ID_DOMAIN = b"pyfmi_interop.model-id.v2\x00"

_SUPPORTED_FORMATS = frozenset(int(member) for member in PayloadFormat)


@dataclass(frozen=True)
class Header:
    """Decoded envelope header.

    ``model_id`` is the derived interface identity, ``instance`` identifies one
    running instance, ``sequence`` orders frames from that instance, and
    ``timestamp_ns`` is the caller's nanosecond timestamp.  ``payload_format``
    names the payload encoding.  The CRC fields are carried so a decoded frame
    can be re-encoded or audited without guessing.
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
    payload_format: int
    flags: int
    reserved: int
    header_crc32: int


@dataclass(frozen=True)
class DecodedFrame:
    """A validated header and its payload bytes."""

    header: Header
    payload: bytes


def model_id(model: ModelDefinition) -> bytes:
    """Derive the 8-byte interface identity of ``model``.

    The identity is the wire interface and nothing else: the model name plus
    the ordered ``(wire field, data type)`` records.  Timing, direction, units,
    rates, capacities, and initial values never enter it, so an adapter's step
    size cannot move its identity.

    The digest input is, in order:

    * the domain separator ``b"pyfmi_interop.model-id.v2\\x00"``;
    * ``model.name`` encoded as UTF-8 followed by one NUL byte;
    * one ``<IB`` record per **wire** signal, ordered by
      ``(value_reference, name)``: the value reference as uint32 followed by
      ``DataType.number`` as uint8.  Parameters are deployment configuration,
      never payload fields, so they do not contribute to the identity.

    The result is the first 8 bytes of the SHA-256 digest.
    """

    digest = hashlib.sha256()
    digest.update(_MODEL_ID_DOMAIN)
    digest.update(model.name.encode("utf-8"))
    digest.update(b"\x00")
    for signal in sorted(
        (
            item
            for item in model.signals
            if item.direction is not Direction.PARAMETER
        ),
        key=lambda item: (item.value_reference, item.name),
    ):
        digest.update(
            struct.pack("<IB", signal.value_reference, signal.data_type.number)
        )
    return digest.digest()[:MODEL_ID_SIZE]


def encode(
    model: ModelDefinition,
    payload: bytes | bytearray | memoryview,
    *,
    instance: int,
    sequence: int,
    timestamp_ns: int,
    payload_format: int | PayloadFormat = PayloadFormat.OPAQUE,
) -> bytes:
    """Wrap ``payload`` in a v2 header and return the complete frame.

    ``instance`` must fit uint32; ``sequence`` and ``timestamp_ns`` must fit
    uint64, and the payload must fit uint32.  ``payload_format`` must be one of
    :class:`PayloadFormat`.  ``flags`` and ``reserved`` are always zero in an
    encoded frame.  Out-of-range values raise :class:`~.FieldRangeError` or
    :class:`~.LengthOverflow`; the codec does not truncate.  The timestamp is
    used verbatim and never read from the clock.
    """

    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    body = bytes(payload)
    _require_uint(instance, 32, "instance")
    _require_uint(sequence, 64, "sequence")
    _require_uint(timestamp_ns, 64, "timestamp_ns")
    format_id = _format_value(payload_format)
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
        format_id,
        0,
        0,
    )
    header_crc32 = zlib.crc32(prefix) & 0xFFFFFFFF
    return prefix + _U32.pack(header_crc32) + body


def decode(buf: bytes | bytearray | memoryview) -> DecodedFrame:
    """Validate ``buf`` as one v2 frame and return its header and payload.

    Checks, in order: fixed-header truncation, magic, wire version, header
    size, flags, reserved, header CRC32, payload format, declared length,
    trailing bytes, payload CRC32.  Every failure is a :class:`~.WireError`
    subclass; a ``struct.error`` never escapes.
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
        payload_format,
        flags,
        reserved,
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
    if flags != 0:
        raise InvalidFlags(f"flags must be zero, got {flags}")
    if reserved != 0:
        raise InvalidReserved(f"reserved must be zero, got {reserved}")
    actual_header_crc32 = zlib.crc32(view[:HEADER_CRC_OFFSET]) & 0xFFFFFFFF
    if actual_header_crc32 != header_crc32:
        raise HeaderChecksumError(
            f"header CRC32 {header_crc32:#010x} != {actual_header_crc32:#010x}"
        )
    if payload_format not in _SUPPORTED_FORMATS:
        raise UnsupportedPayloadFormat(
            f"payload format {payload_format} is not supported "
            f"(opaque=0, protobuf=1, packed=2)"
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
        payload_format=payload_format,
        flags=flags,
        reserved=reserved,
        header_crc32=header_crc32,
    )
    return DecodedFrame(header=header, payload=payload)


def _format_value(value: int | PayloadFormat) -> int:
    if isinstance(value, bool):
        raise FieldRangeError("payload_format must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise FieldRangeError("payload_format must be an integer") from error
    if number not in _SUPPORTED_FORMATS:
        raise FieldRangeError(
            f"payload_format {number} is not supported (opaque=0, protobuf=1, packed=2)"
        )
    return number


def _require_uint(value: Any, bits: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldRangeError(f"{name} must be an integer")
    if not 0 <= value <= (1 << bits) - 1:
        raise FieldRangeError(f"{name} {value} does not fit uint{bits}")
