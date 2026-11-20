"""Compatibility facade for the adapter renderer, now under ``pyfmi_interop.sysml``.

Adapter generation itself lives in :mod:`pyfmi_interop.sysml.parse`
(``generate_adapter``) and :mod:`pyfmi_interop.sysml.adapter`.  The old
``generate_adapter_model`` entry point is gone: callers parse once and pass the
resulting ``ParsedModel`` to ``generate_adapter``.
"""

from __future__ import annotations

from .sysml.adapter import (
    AdapterModel,
    AdapterSignal,
    _strip_default_experiment,
    adapter_from_architecture,
    load_adapter_model,
    render_adapter_cmake,
    render_adapter_hooks,
    render_adapter_wire_json,
    wire_model_from_adapter_json,
)

__all__ = [
    "AdapterModel",
    "AdapterSignal",
    "_strip_default_experiment",
    "adapter_from_architecture",
    "load_adapter_model",
    "render_adapter_cmake",
    "render_adapter_hooks",
    "render_adapter_wire_json",
    "wire_model_from_adapter_json",
]
