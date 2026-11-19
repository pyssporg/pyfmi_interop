"""Identifier mapping shared by the serialization backends.

An FMI signal name is an interface name, not a programming-language
identifier: ports contribute ``port.field`` and arrays contribute ``field[i]``.
Every backend maps that name to its own identifier with :func:`identifier`;
the mapping is collision-checked once per model so two interface names can
never silently share a wire field.
"""

from __future__ import annotations

import re

from ..ir import DataType, Direction, ModelDefinition, ProjectionError, Signal

__all__ = [
    "bool_initial",
    "cpp_data_type",
    "cpp_direction",
    "field_identifiers",
    "float_literal",
    "identifier",
    "message_identifier",
    "member_name",
    "ordered_signals",
    "string_literal",
    "value_expression",
    "wire_direction",
    "wire_signals",
]

_NON_IDENTIFIER = re.compile(r"[^0-9A-Za-z_]")


def identifier(name: str) -> str:
    """Return the backend identifier for an interface signal name.

    ``.`` introduces a field (``port.attr`` -> ``port_attr``), ``[i]`` an array
    element (``port.attr[2]`` -> ``port_attr_2``), and any other non-identifier
    character becomes ``_``.  A leading digit is prefixed with ``_``.
    """

    text = name.replace("]", "").replace(".", "_").replace("[", "_")
    text = _NON_IDENTIFIER.sub("_", text)
    if not text:
        text = "_"
    if text[0].isdigit():
        text = f"_{text}"
    return text


def message_identifier(name: str) -> str:
    """Return the payload message/type identifier for an interface name."""

    return identifier(name)


def field_identifiers(model: ModelDefinition) -> dict[str, str]:
    """Map every signal name to its backend field identifier.

    Iteration is by value reference so the error is deterministic.  Two
    different interface names that map to the same identifier raise
    :class:`~pyfmi_interop.ir.ProjectionError`; the backend never renames one
    of them behind the user's back.
    """

    mapping: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for signal in wire_signals(model):
        field = identifier(signal.name)
        other = claimed.get(field)
        if other is not None and other != signal.name:
            raise ProjectionError(
                f"wire field identifier collision: {other!r} and "
                f"{signal.name!r} both map to {field!r}",
                signal_name=signal.name,
            )
        claimed[field] = signal.name
        mapping[signal.name] = field
    return mapping


def member_name(signal: Signal) -> str:
    """C++ member name for one signal (deterministic, VR-qualified)."""

    return f"m_vr{signal.value_reference}_{identifier(signal.name)}"


def wire_direction(signal: Signal) -> str:
    """Wire direction from the endpoint's point of view.

    FMI causality describes what the *model* exposes; the wire describes what
    the *endpoint* sends.  An FMI input is therefore wire ``out`` and an FMI
    output is wire ``in``.  Parameters travel in neither direction.
    """

    if signal.direction is Direction.INPUT:
        return "out"
    if signal.direction is Direction.OUTPUT:
        return "in"
    return "none"


def ordered_signals(model: ModelDefinition) -> tuple[Signal, ...]:
    """All signals in value-reference order (parameters included)."""

    return tuple(
        sorted(model.signals, key=lambda item: item.value_reference)
    )


def wire_signals(model: ModelDefinition) -> tuple[Signal, ...]:
    """Signals that travel on the wire, in value-reference order.

    Parameters are deployment configuration: they are FMI variables but never
    payload fields, so the descriptor, both codecs, and the model id exclude
    them.  Value references are not reassigned; each remaining field keeps the
    value reference it was authored with.
    """

    return tuple(
        sorted(
            (
                signal
                for signal in model.signals
                if signal.direction is not Direction.PARAMETER
            ),
            key=lambda item: item.value_reference,
        )
    )


def float_literal(value: float) -> str:
    """Deterministic C++ literal for a finite double."""

    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"non-finite floating point value: {number!r}")
    return repr(number)


def string_literal(value: str) -> str:
    """Deterministic C++ string literal with byte-exact octal escapes."""

    chunks: list[str] = []
    for byte in value.encode("utf-8"):
        char = chr(byte)
        if char == "\\":
            chunks.append("\\\\")
        elif char == '"':
            chunks.append('\\"')
        elif char == "\n":
            chunks.append("\\n")
        elif char == "\r":
            chunks.append("\\r")
        elif char == "\t":
            chunks.append("\\t")
        elif 32 <= byte < 127:
            chunks.append(char)
        else:
            chunks.append(f"\\{byte:03o}")
    return '"' + "".join(chunks) + '"'


def cpp_data_type(signal: Signal) -> str:
    return f"pyfmi_interop::DataType::{signal.data_type.value.capitalize()}"


def cpp_direction(signal: Signal) -> str:
    return f"pyfmi_interop::Direction::{signal.direction.value.capitalize()}"


def bool_initial(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def value_expression(signal: Signal) -> str:
    """C++ expression building a runtime ``Value`` from the model member."""

    member = member_name(signal)
    if signal.data_type is DataType.REAL:
        return f"pyfmi_interop::Value::make_real({member})"
    if signal.data_type is DataType.INTEGER:
        return f"pyfmi_interop::Value::make_integer({member})"
    if signal.data_type is DataType.BOOLEAN:
        return f"pyfmi_interop::Value::make_boolean({member})"
    return f"pyfmi_interop::Value::make_string({member}.data())"
