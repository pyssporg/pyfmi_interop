"""The ``wire.json`` descriptor shared by every serialization backend.

The descriptor is a pure function of the model, the backend name, and the
backend format id.  Keys are sorted, floats use ``repr``-stable JSON, and no
timestamp or path is written, so emitting the same model twice is
byte-identical.
"""

from __future__ import annotations

import json
import math

from ..ir import ModelDefinition, ProjectionError
from ..roles import derive_role
from ..wire import model_id
from .naming import (
    field_identifiers,
    message_identifier,
    wire_direction,
    wire_signals,
)

__all__ = [
    "SCHEMA_FORMAT_VERSION",
    "WIRE_JSON_NAME",
    "render_wire_json",
    "wire_json_bytes",
]

#: Version of the descriptor layout itself (not the wire envelope).
SCHEMA_FORMAT_VERSION = 1

#: Fixed descriptor filename; it sits next to the payload schema.
WIRE_JSON_NAME = "wire.json"


def render_wire_json(
    model: ModelDefinition,
    *,
    serialization: str = "protobuf",
    format_id: int = 1,
) -> str:
    """Return the deterministic JSON descriptor for ``model``."""

    _check_signals(model)
    fields = field_identifiers(model)
    signals = wire_signals(model)
    interface = model.interface or model.name
    role = model.role or derive_role(model)
    payload = {
        "format": serialization,
        "format_id": format_id,
        "format_version": SCHEMA_FORMAT_VERSION,
        "guid": model.guid,
        "interface": interface,
        "model": model.name,
        "model_id": model_id(model).hex(),
        "payload_message": message_identifier(interface),
        "proto_package": (
            "pyfmi_interop.wire" if serialization == "protobuf" else None
        ),
        "rate_groups": [
            {
                "name": group.name,
                "period_s": _stable_float(group.period_s, "rate group period_s"),
                "deadline_s": _stable_float(
                    group.deadline_s, "rate group deadline_s"
                ),
                "signals": sorted(group.signals),
            }
            for group in sorted(model.rate_groups, key=lambda item: item.name)
        ],
        "role": role,
        "signals": [
            {
                "id": signal.value_reference,
                "name": signal.name,
                "field": fields[signal.name],
                "wire": wire_direction(signal),
                "data_type": signal.data_type.value,
                "direction": signal.direction.value,
                "rate_hz": (
                    None
                    if signal.rate_hz is None
                    else _stable_float(signal.rate_hz, "signal rate_hz")
                ),
                "unit": signal.unit,
                "capacity": signal.wire_capacity,
            }
            for signal in signals
        ],
    }
    if model.step_size_s is not None:
        payload["step_size_s"] = _stable_float(model.step_size_s, "step_size_s")
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def wire_json_bytes(
    model: ModelDefinition,
    *,
    serialization: str = "protobuf",
    format_id: int = 1,
) -> bytes:
    return render_wire_json(
        model, serialization=serialization, format_id=format_id
    ).encode("utf-8")


def _check_signals(model: ModelDefinition) -> None:
    seen_ids: dict[int, str] = {}
    seen_names: set[str] = set()
    for signal in _ordered(model):
        signal.check_projection()
        if signal.name in seen_names:
            raise ProjectionError("duplicate signal name", signal_name=signal.name)
        previous = seen_ids.get(signal.value_reference)
        if previous is not None:
            raise ProjectionError(
                f"duplicate value reference {signal.value_reference} "
                f"(also used by {previous!r})",
                signal_name=signal.name,
            )
        seen_ids[signal.value_reference] = signal.name
        seen_names.add(signal.name)


def _ordered(model: ModelDefinition):
    return sorted(
        model.signals, key=lambda item: (item.value_reference, item.name)
    )


def _stable_float(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ProjectionError(f"non-finite {label}: {number!r}")
    return 0.0 if number == 0.0 else number
