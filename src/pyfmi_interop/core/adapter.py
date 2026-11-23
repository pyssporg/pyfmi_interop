"""Adapter generation on the ``pyfmi_interfaces`` FMI layer.

This module is the public facade for the adapter plane.  Construction and
validation live in :mod:`pyfmi_interop.core.adapter_model`; JSON, C++, and
CMake emission live in :mod:`pyfmi_interop.core.adapter_render`.  The split
keeps the public import path stable while separating the model side from the
rendering side.

This module is the opt-in replacement for the FMI facade the repository used to
maintain itself (``runtime/src/fmi2_cs_api.cpp``).  ``pyfmi_interfaces`` emits the
FMI 2.0 C interface, the C headers, the bundled FMI headers and
``modelDescription.xml``; this layer supplies the five model hooks and keeps
the wire plane (:mod:`pyfmi_interop.wire`, the serialization backends,
``wire.json``, ``.proto``).

Two value namespaces meet here and are deliberately different:

* **FMI value references** are whatever ``pyfmi_interfaces`` assigns: 0-based,
  declaration order, parameters included.  They are never renumbered.
* **Wire field numbers** are ``1..n`` over the FMI input/output signals only,
  in canonical signal-name order.  Parameters are deployment configuration and
  are never wire fields.

``wire.json`` carries both per signal (``value_reference`` and ``field``), the
schemas use wire field numbers only, and the model id is derived from the wire
field number plus data type so that adding, removing or retyping a parameter
never moves it.

The wire-plane model used by the serialization backends is a regular
:class:`~pyfmi_interop.ir.ModelDefinition` whose value references *are* the
wire field numbers.  The FMI side is carried by the ``pyfmi_interfaces``
``Component`` reduction and recorded in ``model.json``.  A JSON ``model.json``
input has no reduction behind it, so it cannot use this layer; the legacy
facade is its path until that input is retired.
"""

from __future__ import annotations

from pathlib import Path

from .adapter_model import (
    FMI_LAYER,
    AdapterModel,
    AdapterSignal,
    adapter_from_reduction,
    require_fmi_layer,
    select_component,
)
from .adapter_render import (
    adapter_model_json,
    load_adapter_model,
    render_adapter_cmake,
    render_adapter_hooks,
    render_adapter_wire_json,
    wire_model_from_adapter_json,
)
from .serialization.protobuf import render_proto

__all__ = [
    "AdapterModel",
    "AdapterSignal",
    "FMI_LAYER",
    "adapter_from_reduction",
    "adapter_model_json",
    "load_adapter_model",
    "render_adapter_cmake",
    "render_adapter_hooks",
    "render_adapter_wire_json",
    "require_fmi_layer",
    "select_component",
    "wire_model_from_adapter_json",
    "write_adapter_tree",
]


def write_adapter_tree(
    adapter: AdapterModel,
    reduction,
    out_dir: str | Path,
    *,
    prefix: str | None = None,
) -> Path:
    """Write the complete adapter source tree into ``out_dir``.

    The tree is the ``pyfmi_interfaces`` FMI layer (C runtime, headers and
    ``modelDescription.xml``) plus the adapter's own hooks, ``CMakeLists.txt``,
    ``wire.json``, ``model.json`` and, for the protobuf backend, the schema.
    The model description is emitted without ``DefaultExperiment`` because an
    adapter has no step to declare; the emitter option is used directly, with
    no post-processing of the XML.
    """

    helpers = require_fmi_layer()
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    helpers["generate_c_runtime"](
        reduction,
        target,
        component=adapter.identifier,
        prefix=prefix,
    )
    helpers["generate_model_description"](
        reduction,
        target,
        component=adapter.identifier,
        generation_time=None,
        include_default_experiment=False,
    )

    _write_text(target / f"{adapter.stem}_model.cpp", render_adapter_hooks(adapter))
    _write_text(target / "CMakeLists.txt", render_adapter_cmake(adapter))
    _write_text(target / "wire.json", render_adapter_wire_json(adapter))
    (target / "model.json").write_bytes(adapter_model_json(adapter))
    if adapter.serialization == "protobuf":
        _write_text(
            target / f"{adapter.wire_model.name}.proto",
            render_proto(adapter.wire_model),
        )
    return target


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
