"""Deterministic packed payload backend (no third-party dependency).

Layout, in value-reference order:

===========  =================  =============================================
IR type      Encoding           Notes
===========  =================  =============================================
real         ``float64``        little-endian IEEE 754 (``<d``)
integer      ``int32``          little-endian two's complement (``<i``)
boolean      ``uint8``          ``0`` or ``1``
string       ``uint32`` length  little-endian byte count then UTF-8 bytes
             + UTF-8 bytes      bounded by the signal capacity
===========  =================  =============================================

There is no field tag and no padding: the model interface fixes the field
order, so the payload is exactly the concatenation above.  The encoding is a
pure function of the model and the values; equal inputs produce byte-identical
payloads.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..ir import DataType, ModelDefinition, ProjectionError, Signal, fingerprint
from .base import Serialization, write_files
from .descriptor import WIRE_JSON_NAME, wire_json_bytes
from .naming import (
    member_name,
    string_literal,
    wire_signals,
)

__all__ = [
    "PackedSerialization",
    "backend",
    "decode",
    "encode",
]

_DOUBLE = struct.Struct("<d")
_INT32 = struct.Struct("<i")
_UINT8 = struct.Struct("<B")
_UINT32 = struct.Struct("<I")

_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _lookup(values: Mapping[Any, Any], signal: Signal) -> Any:
    if signal.name in values:
        return values[signal.name]
    if signal.value_reference in values:
        return values[signal.value_reference]
    if signal.initial is not None:
        return signal.initial
    if signal.data_type is DataType.STRING:
        return ""
    if signal.data_type is DataType.BOOLEAN:
        return False
    if signal.data_type is DataType.INTEGER:
        return 0
    return 0.0


def _encode_signal(signal: Signal, value: Any) -> bytes:
    if signal.data_type is DataType.REAL:
        return _DOUBLE.pack(float(value))
    if signal.data_type is DataType.INTEGER:
        number = int(value)
        if not _INT32_MIN <= number <= _INT32_MAX:
            raise ProjectionError(
                f"integer {number} does not fit int32", signal_name=signal.name
            )
        return _INT32.pack(number)
    if signal.data_type is DataType.BOOLEAN:
        return _UINT8.pack(1 if bool(value) else 0)
    encoded = str(value).encode("utf-8")
    if len(encoded) > signal.capacity:
        raise ProjectionError(
            f"string value is {len(encoded)} utf-8 bytes, exceeding capacity "
            f"{signal.capacity}",
            signal_name=signal.name,
        )
    return _UINT32.pack(len(encoded)) + encoded


def encode(
    model: ModelDefinition,
    values: Mapping[Any, Any] | None = None,
) -> bytes:
    """Serialize ``values`` into the packed payload for ``model``.

    ``values`` may be keyed by signal name or value reference.  A missing value
    uses the signal's authored initial value, then the type's zero.
    """

    mapping: Mapping[Any, Any] = {} if values is None else values
    return b"".join(
        _encode_signal(signal, _lookup(mapping, signal))
        for signal in wire_signals(model)
    )


def decode(model: ModelDefinition, payload: bytes) -> dict[str, Any]:
    """Decode a packed ``payload`` into ``{signal name: value}``."""

    view = memoryview(payload)
    offset = 0
    result: dict[str, Any] = {}
    for signal in wire_signals(model):
        try:
            if signal.data_type is DataType.REAL:
                value = _DOUBLE.unpack_from(view, offset)[0]
                offset += _DOUBLE.size
            elif signal.data_type is DataType.INTEGER:
                value = _INT32.unpack_from(view, offset)[0]
                offset += _INT32.size
            elif signal.data_type is DataType.BOOLEAN:
                value = bool(_UINT8.unpack_from(view, offset)[0])
                offset += _UINT8.size
            else:
                (length,) = _UINT32.unpack_from(view, offset)
                offset += _UINT32.size
                if length > signal.capacity:
                    raise ProjectionError(
                        f"string field is {length} bytes, exceeding capacity "
                        f"{signal.capacity}",
                        signal_name=signal.name,
                    )
                end = offset + length
                if end > len(view):
                    raise ValueError(
                        f"packed payload ends inside string field {signal.name!r}"
                    )
                value = bytes(view[offset:end]).decode("utf-8")
                offset = end
        except struct.error as error:
            raise ValueError(
                f"packed payload is truncated at field {signal.name!r}"
            ) from error
        result[signal.name] = value
    if offset != len(view):
        raise ValueError(
            f"packed payload has {len(view) - offset} trailing bytes"
        )
    return result


class PackedSerialization(Serialization):
    """The deterministic little-endian packed backend."""

    name = "packed"
    format_id = 2

    def schema_files(self, model: ModelDefinition) -> dict[str, bytes]:
        return {
            WIRE_JSON_NAME: wire_json_bytes(
                model, serialization=self.name, format_id=self.format_id
            )
        }

    def generate_codec(
        self, model: ModelDefinition, out: str | Path, role: str
    ) -> list[Path]:
        files = {
            "model_wire.cpp": _render_model_wire(model),
            "wire_conformance.cpp": _render_wire_conformance(model),
        }
        return write_files(out, files)


backend = PackedSerialization()


def describe(model: ModelDefinition) -> str:
    """Human-readable one-line layout summary (used by docs/tests)."""

    parts = []
    for signal in wire_signals(model):
        if signal.data_type is DataType.REAL:
            parts.append(f"{signal.value_reference}:real=float64")
        elif signal.data_type is DataType.INTEGER:
            parts.append(f"{signal.value_reference}:integer=int32")
        elif signal.data_type is DataType.BOOLEAN:
            parts.append(f"{signal.value_reference}:boolean=uint8")
        else:
            parts.append(f"{signal.value_reference}:string=uint32+utf8")
    return "; ".join(parts)


# Kept for a stable, importable spelling of the real width.
REAL_BYTES = _DOUBLE.size
INTEGER_BYTES = _INT32.size
BOOLEAN_BYTES = _UINT8.size
STRING_LENGTH_BYTES = _UINT32.size


_HEADER = "// Generated by pyfmi-interop. Do not edit by hand.\n"


def _encode_statement(signal: Signal) -> str:
    member = member_name(signal)
    if signal.data_type is DataType.REAL:
        return f"    append_double(payload, {member});"
    if signal.data_type is DataType.INTEGER:
        return f"    append_i32(payload, {member});"
    if signal.data_type is DataType.BOOLEAN:
        return f"    append_bool(payload, {member});"
    return (
        f"    append_u32(payload, static_cast<std::uint32_t>(bounded_length({member})));\n"
        f"    payload.append({member}.data(), bounded_length({member}));"
    )


def _decode_statement(signal: Signal) -> str:
    member = member_name(signal)
    vr = signal.value_reference
    if signal.data_type is DataType.REAL:
        return (
            f"    double value_{vr} = 0.0;\n"
            f"    if (!read_double(payload, offset, value_{vr})) {{\n"
            '        error = "packed payload is truncated";\n'
            "        return false;\n"
            "    }\n"
            f"    {member} = value_{vr};"
        )
    if signal.data_type is DataType.INTEGER:
        return (
            f"    std::int32_t value_{vr} = 0;\n"
            f"    if (!read_i32(payload, offset, value_{vr})) {{\n"
            '        error = "packed payload is truncated";\n'
            "        return false;\n"
            "    }\n"
            f"    {member} = value_{vr};"
        )
    if signal.data_type is DataType.BOOLEAN:
        return (
            f"    bool value_{vr} = false;\n"
            f"    if (!read_bool(payload, offset, value_{vr})) {{\n"
            '        error = "packed payload is truncated";\n'
            "        return false;\n"
            "    }\n"
            f"    {member} = value_{vr};"
        )
    return (
        f"    std::uint32_t length_{vr} = 0;\n"
        f"    if (!read_u32(payload, offset, length_{vr})) {{\n"
        '        error = "packed payload is truncated";\n'
        "        return false;\n"
        "    }\n"
        f"    if (length_{vr} > {member}.size() - 1u ||\n"
        f"        static_cast<std::size_t>(length_{vr}) > payload.size() - offset) {{\n"
        '        error = "packed string exceeds capacity or payload";\n'
        "        return false;\n"
        "    }\n"
        f"    copy_bounded({member}.data(), {member}.size(),\n"
        f"                 std::string_view(payload.data() + offset, length_{vr}));\n"
        f"    offset += length_{vr};"
    )


def _render_model_wire(model: ModelDefinition) -> str:
    signals = wire_signals(model)
    records = ", ".join(
        f"{{{signal.value_reference}u, {signal.data_type.number}u}}"
        for signal in signals
    )
    encode_lines = "\n".join(_encode_statement(signal) for signal in signals)
    decode_lines = "\n".join(_decode_statement(signal) for signal in signals)
    if not encode_lines:
        encode_lines = "    (void)payload;"
    if not decode_lines:
        decode_lines = "    (void)payload;\n    (void)offset;"
    return (
        _HEADER
        + f"// Model: {model.name}\n"
        + f"// IR fingerprint: {fingerprint(model)}\n"
        + "//\n"
        + "// Packed payload layer: little-endian, no tags, fields in value-reference\n"
        + "// order.  The mirror implementation is pyfmi_interop.serialization.packed.\n"
        + '#include "model_runtime.hpp"\n'
        + "\n"
        + '#include "pyfmi_interop/runtime/wire.hpp"\n'
        + "\n"
        + "#include <array>\n"
        + "#include <cstddef>\n"
        + "#include <cstdint>\n"
        + "#include <cstring>\n"
        + "#include <limits>\n"
        + "#include <string>\n"
        + "#include <string_view>\n"
        + "#include <vector>\n"
        + "\n"
        + "namespace {\n"
        + "\n"
        + f"constexpr char kModelName[] = {string_literal(model.name)};\n"
        + "\n"
        + "template <std::size_t N>\n"
        + "std::size_t bounded_length(const std::array<char, N>& value) {\n"
        + "    std::size_t length = 0;\n"
        + "    while (length < N && value[length] != '\\0') {\n"
        + "        ++length;\n"
        + "    }\n"
        + "    return length;\n"
        + "}\n"
        + "\n"
        + "void append_u32(std::string& out, std::uint32_t value) {\n"
        + "    for (int shift = 0; shift < 32; shift += 8) {\n"
        + "        out.push_back(static_cast<char>((value >> shift) & 0xFFu));\n"
        + "    }\n"
        + "}\n"
        + "\n"
        + "void append_i32(std::string& out, std::int32_t value) {\n"
        + "    append_u32(out, static_cast<std::uint32_t>(value));\n"
        + "}\n"
        + "\n"
        + "void append_double(std::string& out, double value) {\n"
        + "    std::uint64_t bits = 0;\n"
        + "    std::memcpy(&bits, &value, sizeof(bits));\n"
        + "    for (int shift = 0; shift < 64; shift += 8) {\n"
        + "        out.push_back(static_cast<char>((bits >> shift) & 0xFFu));\n"
        + "    }\n"
        + "}\n"
        + "\n"
        + "void append_bool(std::string& out, bool value) {\n"
        + "    out.push_back(value ? '\\1' : '\\0');\n"
        + "}\n"
        + "\n"
        + "bool read_u32(std::string_view payload, std::size_t& offset,\n"
        + "              std::uint32_t& out) {\n"
        + "    if (payload.size() - offset < 4u) {\n"
        + "        return false;\n"
        + "    }\n"
        + "    out = 0;\n"
        + "    for (int index = 0; index < 4; ++index) {\n"
        + "        out |= static_cast<std::uint32_t>(\n"
        + "                   static_cast<unsigned char>(payload[offset + index]))\n"
        + "               << (8 * index);\n"
        + "    }\n"
        + "    offset += 4u;\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "bool read_i32(std::string_view payload, std::size_t& offset,\n"
        + "              std::int32_t& out) {\n"
        + "    std::uint32_t raw = 0;\n"
        + "    if (!read_u32(payload, offset, raw)) {\n"
        + "        return false;\n"
        + "    }\n"
        + "    std::memcpy(&out, &raw, sizeof(out));\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "bool read_double(std::string_view payload, std::size_t& offset,\n"
        + "                 double& out) {\n"
        + "    if (payload.size() - offset < 8u) {\n"
        + "        return false;\n"
        + "    }\n"
        + "    std::uint64_t bits = 0;\n"
        + "    for (int index = 0; index < 8; ++index) {\n"
        + "        bits |= static_cast<std::uint64_t>(\n"
        + "                    static_cast<unsigned char>(payload[offset + index]))\n"
        + "                << (8 * index);\n"
        + "    }\n"
        + "    offset += 8u;\n"
        + "    std::memcpy(&out, &bits, sizeof(out));\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "bool read_bool(std::string_view payload, std::size_t& offset, bool& out) {\n"
        + "    if (payload.size() - offset < 1u) {\n"
        + "        return false;\n"
        + "    }\n"
        + "    out = static_cast<unsigned char>(payload[offset]) != 0u;\n"
        + "    offset += 1u;\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "const std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize>& wire_model_id() {\n"
        + "    static const std::array<std::uint8_t, pyfmi_interop::wire::kModelIdSize> id =\n"
        + "        pyfmi_interop::wire::model_id(\n"
        + "            std::string_view(kModelName),\n"
        + "            std::vector<pyfmi_interop::wire::ModelIdSignal>{" + records + "});\n"
        + "    return id;\n"
        + "}\n"
        + "\n"
        + "}  // namespace\n"
        + "\n"
        + "bool GeneratedModelRuntime::encode_wire_payload(std::string& payload,\n"
        + "                                                std::string& error) const {\n"
        + "    error.clear();\n"
        + "    payload.clear();\n"
        + encode_lines
        + "\n"
        + "    if (payload.size() > std::numeric_limits<std::uint32_t>::max()) {\n"
        + '        error = "payload exceeds uint32 length";\n'
        + "        return false;\n"
        + "    }\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "bool GeneratedModelRuntime::decode_wire_payload(std::string_view payload,\n"
        + "                                                std::string& error) {\n"
        + "    error.clear();\n"
        + "    std::size_t offset = 0;\n"
        + decode_lines
        + "\n"
        + "    if (offset != payload.size()) {\n"
        + '        error = "packed payload has trailing bytes";\n'
        + "        return false;\n"
        + "    }\n"
        + "    return true;\n"
        + "}\n"
        + "\n"
        + "std::vector<std::uint8_t> GeneratedModelRuntime::encode_wire_frame(\n"
        + "    std::uint32_t instance, std::uint64_t sequence, std::uint64_t timestamp_ns,\n"
        + "    std::string& error) const {\n"
        + "    error.clear();\n"
        + "    std::string payload;\n"
        + "    if (!encode_wire_payload(payload, error)) {\n"
        + "        return {};\n"
        + "    }\n"
        + "    pyfmi_interop::wire::EncodeResult result = pyfmi_interop::wire::encode_frame(\n"
        + "        wire_model_id(), payload, instance, sequence, timestamp_ns,\n"
        + "        pyfmi_interop::wire::PayloadFormat::Packed);\n"
        + "    if (!result) {\n"
        + "        error = result.error.message;\n"
        + "        return {};\n"
        + "    }\n"
        + "    return std::move(result.frame);\n"
        + "}\n"
        + "\n"
        + "bool GeneratedModelRuntime::decode_wire_frame(\n"
        + "    const std::vector<std::uint8_t>& frame, std::string& error) {\n"
        + "    error.clear();\n"
        + "    const std::string_view buffer(\n"
        + "        reinterpret_cast<const char*>(frame.data()), frame.size());\n"
        + "    pyfmi_interop::wire::DecodeResult result =\n"
        + "        pyfmi_interop::wire::decode_frame(buffer);\n"
        + "    if (!result) {\n"
        + "        error = result.error.message;\n"
        + "        return false;\n"
        + "    }\n"
        + "    if (result.frame.header.model_id != wire_model_id()) {\n"
        + '        error = "model id mismatch";\n'
        + "        return false;\n"
        + "    }\n"
        + "    if (result.frame.header.payload_format !=\n"
        + "        pyfmi_interop::wire::PayloadFormat::Packed) {\n"
        + '        error = "payload format mismatch";\n'
        + "        return false;\n"
        + "    }\n"
        + "    const std::string_view payload(\n"
        + "        reinterpret_cast<const char*>(result.frame.payload.data()),\n"
        + "        result.frame.payload.size());\n"
        + "    return decode_wire_payload(payload, error);\n"
        + "}\n"
    )


def _render_wire_conformance(model: ModelDefinition) -> str:
    return (
        _HEADER
        + f"// Model: {model.name}\n"
        + "//\n"
        + "// Prints the hex of one packed wire frame encoded from the reset state.\n"
        + '#include "model_runtime.hpp"\n'
        + "\n"
        + "#include <cstdio>\n"
        + "#include <string>\n"
        + "#include <vector>\n"
        + "\n"
        + "int main() {\n"
        + "    GeneratedModelRuntime model;\n"
        + "    model.reset();\n"
        + "    std::string error;\n"
        + "    const std::vector<std::uint8_t> frame =\n"
        + "        model.encode_wire_frame(7u, 42u, 1700000000000000000ULL, error);\n"
        + "    if (!error.empty() || frame.empty()) {\n"
        + '        std::fprintf(stderr, "wire encode failed: %s\\n", error.c_str());\n'
        + "        return 1;\n"
        + "    }\n"
        + "    for (const std::uint8_t byte : frame) {\n"
        + '        std::printf("%02x", byte);\n'
        + "    }\n"
        + '    std::printf("\\n");\n'
        + "    return 0;\n"
        + "}\n"
    )
