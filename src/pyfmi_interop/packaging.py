"""Package a built model and its IR into a deterministic FMI 2.0 ``.fmu``.

The realtime FMU differs from the SysML artifact packages: this repository owns
its own FMI XML and does not depend on an external FMI library.  The archive is
written from an in-memory table with fixed timestamps, sorted names, and a
fixed permission mask, so packaging the same inputs twice yields identical
bytes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .ir import (
    DataType,
    Direction,
    ModelDefinition,
    Signal,
    fingerprint,
    model_from_dict,
    model_to_dict,
)
from .schema import schema_entries

__all__ = [
    "package_fmu",
    "platform_binary_dir",
    "platform_library_extension",
    "render_model_description",
]

_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def platform_binary_dir() -> str:
    """Return the FMI platform directory for the host."""

    if sys.platform.startswith("linux"):
        return "linux64"
    if sys.platform == "darwin":
        return "darwin64"
    if sys.platform == "win32":
        return "win64"
    raise RuntimeError(f"unsupported platform: {sys.platform}")


def platform_library_extension() -> str:
    platform = platform_binary_dir()
    if platform == "linux64":
        return ".so"
    if platform == "darwin64":
        return ".dylib"
    return ".dll"


def package_fmu(
    model_dir: str | Path,
    library: str | Path,
    out_path: str | Path,
    *,
    model: ModelDefinition | None = None,
) -> Path:
    """Write ``out_path`` from a generated model directory and shared library."""

    destination = Path(out_path)
    binary = Path(library)
    if not binary.is_file():
        raise FileNotFoundError(f"shared library does not exist: {binary}")

    if model is None:
        model = _load_model(Path(model_dir))
    model.validate()

    platform_dir = platform_binary_dir()
    extension = platform_library_extension()
    binary_arcname = f"binaries/{platform_dir}/{model.name}{extension}"

    entries: dict[str, bytes] = {
        "modelDescription.xml": render_model_description(model).encode("utf-8"),
        "resources/model.json": _canonical_model_json(model),
        "resources/runtime.json": _runtime_json(model, binary_arcname, platform_dir),
        binary_arcname: binary.read_bytes(),
    }
    # The schema travels with the binary: a third-party decoder needs only the
    # packaged artifacts, never this Python package.
    entries.update(schema_entries(model, prefix=f"binaries/{platform_dir}"))

    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(
        destination,
        "w",
        compression=ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in sorted(entries):
            archive.writestr(_zip_info(name), entries[name])

    return destination


def _load_model(model_dir: Path) -> ModelDefinition:
    model_json = model_dir / "model.json"
    if not model_json.is_file():
        raise FileNotFoundError(f"model.json not found in model directory: {model_dir}")
    payload = json.loads(model_json.read_text(encoding="utf-8"))
    return model_from_dict(payload)


def _canonical_model_json(model: ModelDefinition) -> bytes:
    text = json.dumps(model_to_dict(model), indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _runtime_json(
    model: ModelDefinition,
    binary_arcname: str,
    platform_dir: str,
) -> bytes:
    payload = {
        "modelName": model.name,
        "modelIdentifier": model.name,
        "guid": model.guid,
        "fingerprint": fingerprint(model),
        "binary": binary_arcname,
        "platform": platform_dir,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=_FIXED_DATE_TIME)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3  # Unix, so the mode below is meaningful.
    info.external_attr = 0o644 << 16
    return info


def render_model_description(model: ModelDefinition) -> str:
    """Return a deterministic FMI 2.0 ``modelDescription.xml`` document."""

    root = Element(
        "fmiModelDescription",
        {
            "fmiVersion": "2.0",
            "modelName": model.name,
            "guid": model.guid,
            "generationTool": "pyfmi-interop",
            "variableNamingConvention": "structured",
        },
    )
    if model.description:
        root.set("description", model.description)

    SubElement(
        root,
        "CoSimulation",
        {
            "modelIdentifier": model.name,
            "canHandleVariableCommunicationStepSize": "true",
            "canGetAndSetFMUstate": "false",
            "canSerializeFMUstate": "false",
            "providesDirectionalDerivative": "false",
        },
    )
    SubElement(
        root,
        "DefaultExperiment",
        {"startTime": "0", "stepSize": _format_real(model.step_size_s)},
    )

    model_variables = SubElement(root, "ModelVariables")
    outputs: list[int] = []
    for position, signal in enumerate(
        sorted(model.signals, key=lambda item: item.value_reference),
        start=1,
    ):
        variable = SubElement(
            model_variables,
            "ScalarVariable",
            {
                "name": signal.name,
                "valueReference": str(signal.value_reference),
                "causality": signal.direction.value,
                "variability": _variability(signal),
            },
        )
        data = SubElement(variable, _type_name(signal.data_type))
        if signal.unit:
            data.set("unit", signal.unit)
        start = _start_value(signal)
        if start is not None:
            data.set("start", start)
        if signal.direction is Direction.OUTPUT:
            outputs.append(position)

    model_structure = SubElement(root, "ModelStructure")
    if outputs:
        outputs_element = SubElement(model_structure, "Outputs")
        for index in outputs:
            SubElement(outputs_element, "Unknown", {"index": str(index)})

    text = tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + text + "\n"


def _variability(signal: Signal) -> str:
    if signal.direction is Direction.PARAMETER:
        return "tunable"
    if signal.data_type is DataType.REAL:
        return "continuous"
    return "discrete"


def _type_name(data_type: DataType) -> str:
    return {
        DataType.REAL: "Real",
        DataType.INTEGER: "Integer",
        DataType.BOOLEAN: "Boolean",
        DataType.STRING: "String",
    }[data_type]


def _start_value(signal: Signal) -> str | None:
    if signal.initial is None:
        return None
    if signal.data_type is DataType.REAL:
        return _format_real(float(signal.initial))
    if signal.data_type is DataType.INTEGER:
        return str(int(signal.initial))
    if signal.data_type is DataType.BOOLEAN:
        return "true" if signal.initial else "false"
    return str(signal.initial)


def _format_real(value: float) -> str:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"non-finite floating point value: {number!r}")
    return repr(number)
