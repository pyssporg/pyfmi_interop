"""Wire envelope: the byte framing that carries an opaque protobuf payload.

The public surface is :func:`encode`, :func:`decode`, :func:`model_id`, the
:class:`Header` / :class:`DecodedFrame` records, the :data:`HEADER_SIZE` and
:data:`WIRE_VERSION` constants, and the :class:`WireError` taxonomy.  See
``docs/wire.md`` for the byte layout and the model-id and CRC definitions.
"""

from __future__ import annotations

from .codec import (
    HEADER_SIZE,
    MODEL_ID_SIZE,
    WIRE_MAGIC,
    WIRE_VERSION,
    DecodedFrame,
    Header,
    decode,
    encode,
    model_id,
)
from .errors import (
    ChecksumError,
    FieldRangeError,
    HeaderChecksumError,
    InvalidHeaderSize,
    InvalidMagic,
    LengthOverflow,
    PayloadChecksumError,
    TrailingBytes,
    TruncatedFrame,
    UnsupportedWireVersion,
    WireError,
)

__all__ = [
    "ChecksumError",
    "DecodedFrame",
    "FieldRangeError",
    "HEADER_SIZE",
    "Header",
    "HeaderChecksumError",
    "InvalidHeaderSize",
    "InvalidMagic",
    "LengthOverflow",
    "MODEL_ID_SIZE",
    "PayloadChecksumError",
    "TrailingBytes",
    "TruncatedFrame",
    "UnsupportedWireVersion",
    "WIRE_MAGIC",
    "WIRE_VERSION",
    "WireError",
    "decode",
    "encode",
    "model_id",
]
