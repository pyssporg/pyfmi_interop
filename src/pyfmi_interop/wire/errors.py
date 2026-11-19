"""Typed failures of the wire envelope.

Every exception here derives from :class:`WireError`, so a caller that only
wants "this frame is not usable" catches one type.  The subclasses exist so
diagnostics and tests can name the exact defect; :func:`decode` never lets a
``struct.error`` escape.
"""

from __future__ import annotations

__all__ = [
    "ChecksumError",
    "FieldRangeError",
    "HeaderChecksumError",
    "InvalidHeaderSize",
    "InvalidMagic",
    "LengthOverflow",
    "PayloadChecksumError",
    "TrailingBytes",
    "TruncatedFrame",
    "UnsupportedWireVersion",
    "WireError",
]


class WireError(Exception):
    """Base class for every wire-envelope failure."""


class InvalidMagic(WireError):
    """The frame does not start with :data:`~.WIRE_MAGIC`."""


class UnsupportedWireVersion(WireError):
    """The frame names a wire version this codec does not implement."""


class InvalidHeaderSize(WireError):
    """The frame's header-size field is not :data:`~.HEADER_SIZE`."""


class TruncatedFrame(WireError):
    """The buffer is shorter than the fixed header."""


class LengthOverflow(WireError):
    """The declared payload length is impossible or exceeds the buffer."""


class TrailingBytes(WireError):
    """The buffer holds more bytes than the declared frame."""


class ChecksumError(WireError):
    """A CRC32 check failed."""


class HeaderChecksumError(ChecksumError):
    """The header CRC32 does not match the preceding header bytes."""


class PayloadChecksumError(ChecksumError):
    """The payload CRC32 does not match the payload bytes."""


class FieldRangeError(WireError):
    """A value passed to :func:`~.encode` does not fit its header field."""
