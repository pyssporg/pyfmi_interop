"""The opt-in ``psysml2`` FMI layer: two namespaces, one wire plane.

These tests assert against the emitted tree and the packed ``.fmu``, not an
intermediate string: the FMI interface belongs to ``pyfmi_sysml2`` while the
wire field numbers, ``wire.json``, the schema and the packaging stay here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

from pyfmi_interop import Direction, generate_model, package_fmu
from pyfmi_interop.packaging import platform_binary_dir
from pyfmi_interop.psysml2 import (
    load_adapter_model,
    wire_model_from_adapter_json,
)

pytestmark = [pytest.mark.cpp, pytest.mark.system]

_EXAMPLE = (
    Path(__file__).resolve().parents[1] / "examples" / "adapter" / "actuator_link.sysml"
)

_CHAIN_LIBRARY = """\
package ChainLibrary {
  private import ScalarValues::*;

  port def Signal {
    attribute value : Real;
  }

  part def FmuModel {
  }

  part def FmuInterop :> FmuModel {
  }

  part def Leaf :> FmuInterop {
    in port command : Signal;
    out port status : Signal;
  }
}
"""

_CHAIN_APP = """\
package ChainApp {
  private import ChainLibrary::*;
}
"""


def _write_chain(tmp_path: Path) -> tuple[Path, Path]:
    library = tmp_path / "chain_library.sysml"
    app = tmp_path / "chain_app.sysml"
    library.write_text(_CHAIN_LIBRARY, encoding="utf-8")
    app.write_text(_CHAIN_APP, encoding="utf-8")
    return app, library


@pytest.fixture(scope="module")
def example():
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    return sysml.load_model(_EXAMPLE, name="ActuatorLinkAdapter")


def _generate(model, out: Path, *, serialization: str = "packed", source=_EXAMPLE):
    return generate_model(
        model,
        out,
        serialization=serialization,
        fmi_layer="psysml2",
        sysml_source=source,
    )


def test_example_uses_the_shared_interop_library(example, tmp_path):
    text = _EXAMPLE.read_text(encoding="utf-8")

    assert "private import PyfmiInterop::*;" in text
    assert "part def ActuatorLink :> FmuInterop {" in text
    assert "port def InteropDeployment" not in text
    assert "part def FmuModel" not in text
    assert "BenchDefaults" not in text
    assert "part def Root" not in text

    target = _generate(example, tmp_path)
    payload = load_adapter_model(target)
    assert payload["model_name"] == "ActuatorLink"


def test_inline_model_importing_the_library_generates(tmp_path):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    source = tmp_path / "inline.sysml"
    source.write_text(
        "package InlineInterop {\n"
        "  private import ScalarValues::*;\n"
        "  private import PyfmiInterop::*;\n"
        "\n"
        "  port def Command {\n"
        "    attribute demand : Real;\n"
        "  }\n"
        "\n"
        "  port def Status {\n"
        "    attribute actual : Real;\n"
        "  }\n"
        "\n"
        "  part def Widget :> FmuInterop {\n"
        "    in port command : Command;\n"
        "    out port status : Status;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    model = sysml.load_model(source, name="WidgetAdapter", realtime=False)
    target = _generate(model, tmp_path / "inline", source=source)
    wire = json.loads((target / "wire.json").read_text(encoding="utf-8"))
    description = (target / "Widget" / "modelDescription.xml").read_text(
        encoding="utf-8"
    )

    assert model.interface == "Widget"
    assert {item["name"] for item in wire["parameters"]} == {
        "transport",
        "bind_address",
        "peer_address",
    }
    assert {item["name"] for item in wire["signals"]} == {
        "command.demand",
        "status.actual",
    }
    assert 'modelName="Widget"' in description


def test_fmi_layer_requires_a_sysml_source(example, tmp_path):
    with pytest.raises(ValueError, match="source="):
        generate_model(example, tmp_path, fmi_layer="psysml2")


@pytest.mark.component
def test_library_defined_fmu_loads_and_generates_from_includes(tmp_path):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    app, library = _write_chain(tmp_path)
    model = sysml.load_model(app, includes=[library], realtime=False)

    assert model.interface == "Leaf"
    assert {item.name: item.direction for item in model.signals} == {
        "command": Direction.INPUT,
        "status": Direction.OUTPUT,
    }

    target = generate_model(
        model,
        tmp_path / "generated",
        serialization="packed",
        fmi_layer="psysml2",
        sysml_source=app,
        sysml_includes=[library],
    )
    document = (target / "Leaf" / "modelDescription.xml").read_text(encoding="utf-8")
    payload = load_adapter_model(target)

    assert 'modelName="Leaf"' in document
    assert payload["model_name"] == "Leaf"
    assert {item["name"] for item in payload["signals"] if item["field"] is not None} == {
        "command",
        "status",
    }


@pytest.mark.component
def test_model_without_includes_is_unchanged(example, tmp_path):
    plain = _generate(example, tmp_path / "plain")
    empty = generate_model(
        example,
        tmp_path / "empty",
        serialization="packed",
        fmi_layer="psysml2",
        sysml_source=_EXAMPLE,
        sysml_includes=(),
    )

    plain_files = sorted(
        path.relative_to(plain) for path in plain.rglob("*") if path.is_file()
    )
    empty_files = sorted(
        path.relative_to(empty) for path in empty.rglob("*") if path.is_file()
    )
    assert plain_files == empty_files
    for name in plain_files:
        assert (plain / name).read_bytes() == (empty / name).read_bytes(), str(name)
    document = (plain / "ActuatorLink" / "modelDescription.xml").read_text(
        encoding="utf-8"
    )
    assert 'modelName="ActuatorLink"' in document


def test_tree_carries_both_namespaces_per_signal(example, tmp_path):
    target = _generate(example, tmp_path)
    wire = json.loads((target / "wire.json").read_text(encoding="utf-8"))
    model = load_adapter_model(target)

    assert wire["fmi_layer"] == "psysml2"
    assert {item["name"] for item in wire["parameters"]} == {
        "transport",
        "bind_address",
        "peer_address",
    }
    wire_signals = wire["signals"]
    assert [item["field"] for item in wire_signals] == list(
        range(1, len(wire_signals) + 1)
    )
    # Canonical signal-name order is the wire field order.
    assert [item["name"] for item in wire_signals] == sorted(
        item["name"] for item in wire_signals
    )
    # FMI value references are the 0-based pyfmi_sysml2 ones and are not
    # renumbered to the field numbers.
    assert all(isinstance(item["value_reference"], int) for item in wire_signals)
    assert wire_signals[0]["value_reference"] != wire_signals[0]["field"]

    parameters = {item["name"]: item for item in model["signals"] if item["field"] is None}
    assert parameters["transport"]["value_reference"] == 0
    assert "field" in model["signals"][0]


def test_generated_hooks_cover_the_five_seams(example, tmp_path):
    target = _generate(example, tmp_path)
    hooks = next(target.glob("*_model.cpp")).read_text(encoding="utf-8")

    for name in (
        "model_initialize",
        "model_do_step",
        "model_terminate",
        "model_reset",
        "model_free",
    ):
        assert name in hooks
    assert "user_data" in hooks
    assert "user_step" not in hooks
    assert "make_transport" in hooks
    assert "wire::encode_frame" in hooks
    assert "wire::decode_frame" in hooks


def test_parameter_addition_moves_vrs_not_fields_or_model_id(tmp_path):
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    original = _EXAMPLE.read_text(encoding="utf-8")
    # A derived deployment interface adds a parameter while keeping the shared
    # InteropDeployment fields; the part points its parameters port at it.
    extended = original.replace(
        "  port def Command {",
        "  port def ExtendedDeployment :> InteropDeployment {\n"
        '    attribute protocol : String = "v1";\n'
        "  }\n\n"
        "  port def Command {",
    ).replace(
        "  part def ActuatorLink :> FmuInterop {",
        "  part def ActuatorLink :> FmuInterop {\n"
        "    in port parameters : ExtendedDeployment;",
    )
    assert extended != original

    source_a = tmp_path / "a.sysml"
    source_b = tmp_path / "b.sysml"
    source_a.write_text(original, encoding="utf-8")
    source_b.write_text(extended, encoding="utf-8")
    model_a = sysml.load_model(source_a, name="ActuatorLinkAdapter")
    model_b = sysml.load_model(source_b, name="ActuatorLinkAdapter")

    out_a = _generate(model_a, tmp_path / "a", source=source_a)
    out_b = _generate(model_b, tmp_path / "b", source=source_b)
    wire_a = json.loads((out_a / "wire.json").read_text(encoding="utf-8"))
    wire_b = json.loads((out_b / "wire.json").read_text(encoding="utf-8"))

    assert wire_a["model_id"] == wire_b["model_id"]
    assert [item["field"] for item in wire_a["signals"]] == [
        item["field"] for item in wire_b["signals"]
    ]
    assert [item["value_reference"] for item in wire_a["signals"]] != [
        item["value_reference"] for item in wire_b["signals"]
    ]
    assert any(
        item["name"].endswith("protocol") for item in wire_b["parameters"]
    )


def test_protobuf_schema_uses_wire_field_numbers(example, tmp_path):
    pytest.importorskip("grpc_tools", reason="protoc is not installed")
    target = _generate(example, tmp_path, serialization="protobuf")
    wire = json.loads((target / "wire.json").read_text(encoding="utf-8"))
    proto = next(target.glob("*.proto")).read_text(encoding="utf-8")
    fields = {
        int(match.group(2)): match.group(1)
        for match in re.finditer(r"^  Value (\w+) = (\d+);$", proto, re.MULTILINE)
    }
    assert set(fields) == {item["field"] for item in wire["signals"]}


def test_generation_is_byte_deterministic(example, tmp_path):
    first = _generate(example, tmp_path / "first")
    second = _generate(example, tmp_path / "second")

    names = sorted(
        path.relative_to(first)
        for path in first.rglob("*")
        if path.is_file()
    )
    assert names
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), str(name)


def test_packaged_archive_uses_the_sysml2_model_description(example, tmp_path):
    target = _generate(example, tmp_path)
    library = tmp_path / "libActuatorLink.so"
    library.write_bytes(b"\x7fELF fake adapter")
    payload = load_adapter_model(target)
    model = wire_model_from_adapter_json(payload)
    platform = platform_binary_dir()
    description = (target / "ActuatorLink" / "modelDescription.xml").read_bytes()
    entries = {
        f"binaries/{platform}/wire.json": (target / "wire.json").read_bytes()
    }

    def package(path: Path) -> Path:
        return package_fmu(
            target,
            library,
            path,
            model=model,
            model_description=description,
            model_json=(target / "model.json").read_bytes(),
            model_name=payload["model_name"],
            extra_entries=entries,
            include_schema=False,
        )

    first = package(tmp_path / "first.fmu")
    second = package(tmp_path / "second.fmu")
    assert first.read_bytes() == second.read_bytes()

    with ZipFile(first) as archive:
        names = set(archive.namelist())
        assert "modelDescription.xml" in names
        assert f"binaries/{platform}/wire.json" in names
        assert f"binaries/{platform}/ActuatorLink{_extension()}" in names
        document = archive.read("modelDescription.xml").decode("utf-8")
        descriptor = json.loads(
            archive.read(f"binaries/{platform}/wire.json").decode("utf-8")
        )
    assert 'modelName="ActuatorLink"' in document
    assert 'modelName="Root.ActuatorLink"' not in document
    assert 'modelIdentifier="ActuatorLink"' in document
    guid = re.search(r'guid="([^"]+)"', document).group(1)
    assert guid == _direct_guid("ActuatorLink")
    assert {"value_reference", "field"} <= set(descriptor["signals"][0])


def _generate_variant(tmp_path, name: str, text: str):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    source = tmp_path / f"{name}.sysml"
    source.write_text(text, encoding="utf-8")
    model = sysml.load_model(source, name="ActuatorLinkAdapter", realtime=False)
    target = _generate(model, tmp_path / name, source=source)
    return target, json.loads((target / "wire.json").read_text(encoding="utf-8"))


def test_adapter_model_id_ignores_step_size_and_declared_rates(tmp_path):
    original = _EXAMPLE.read_text(encoding="utf-8")
    _, base = _generate_variant(tmp_path, "base", original)

    stepped_text = original.replace(
        "  port def Command {",
        "  attribute def BuildTiming;\n\n"
        "  port def Command {",
    ).replace(
        "  part def ActuatorLink :> FmuInterop {",
        "  part def ActuatorLink :> FmuInterop {\n"
        "    attribute step_size_s : BuildTiming = 0.002;",
    )
    rated_text = original.replace(
        "  port def Command {",
        "  attribute def PortTiming :> ParameterSet;\n\n"
        "  port def Command {\n"
        "    attribute rate : PortTiming = 250.0;",
    )
    assert stepped_text != original and rated_text != original

    _, stepped = _generate_variant(tmp_path, "stepped", stepped_text)
    _, rated = _generate_variant(tmp_path, "rated", rated_text)

    assert stepped["step_size_s"] == 0.002
    assert rated["signals"] != base["signals"]
    assert base["model_id"] == stepped["model_id"] == rated["model_id"]


def test_adapter_document_has_no_default_experiment(tmp_path):
    original = _EXAMPLE.read_text(encoding="utf-8")
    text = original.replace(
        "  part def ActuatorLink :> FmuInterop {",
        "  attribute def AdapterDefaults :> DefaultExperiment {\n"
        "    attribute startTime = 0.0;\n"
        "    attribute stopTime = 1.0;\n"
        "  }\n\n"
        "  part def ActuatorLink :> FmuInterop {\n"
        "    attribute defaults : AdapterDefaults;",
    )
    assert text != original

    target, _ = _generate_variant(tmp_path, "experiment", text)
    document = (target / "ActuatorLink" / "modelDescription.xml").read_text(
        encoding="utf-8"
    )
    assert "DefaultExperiment" not in document


def test_adapter_rejects_a_rate_that_is_not_a_multiple_of_the_slowest(tmp_path):
    original = _EXAMPLE.read_text(encoding="utf-8")
    text = original.replace(
        "  port def Command {",
        "  attribute def PortTiming :> ParameterSet;\n\n"
        "  port def Command {\n"
        "    attribute rate : PortTiming = 250.0;",
    ).replace(
        "  port def Feedback {",
        "  port def Feedback {\n"
        "    attribute rate : PortTiming = 100.0;",
    )
    assert text != original

    with pytest.raises(ValueError, match="integer multiple"):
        _generate_variant(tmp_path, "misaligned", text)


def test_adapter_generates_without_a_step_size(tmp_path):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    model = sysml.load_model(_EXAMPLE, name="ActuatorLinkAdapter", realtime=False)
    target = _generate(model, tmp_path / "no-step")
    hooks = next(target.glob("*_model.cpp")).read_text(encoding="utf-8")

    assert "kStepSize" not in hooks
    assert (target / "wire.json").is_file()


def _direct_guid(component: str) -> str:
    from pyfmi_sysml2.core.identity import component_guid

    return component_guid("ActuatorLinkExample", component, direct=True)


def _extension() -> str:
    from pyfmi_interop.packaging import platform_library_extension

    return platform_library_extension()


_SYSTEM_EXAMPLE = (
    Path(__file__).resolve().parents[1] / "examples" / "system" / "bench.sysml"
)

_SYSTEM_UNITS = ["ActuatorLink", "Controller", "SensorLink"]


def _system_architecture():
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop.sysml import load_architecture

    return load_architecture(_SYSTEM_EXAMPLE)


def _generate_unit(architecture, unit: str, out: Path, *, serialization="packed"):
    from pyfmi_interop.sysml import model_from_architecture

    model = model_from_architecture(
        architecture,
        composition=unit,
        name=unit,
        realtime=False,
    )
    target = generate_model(
        model,
        out,
        serialization=serialization,
        fmi_layer="psysml2",
        sysml_source=architecture,
        composition=unit,
    )
    return model, target


def test_fmu_units_lists_the_three_system_units_sorted():
    architecture = _system_architecture()
    from pyfmi_sysml2.core import fmu_units

    assert [definition.name for definition in fmu_units(architecture)] == _SYSTEM_UNITS


def test_load_model_composition_selects_only_that_units_signals():
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    model = sysml.load_model(
        _SYSTEM_EXAMPLE,
        composition="Controller",
        name="Controller",
        realtime=False,
    )

    assert model.interface == "Controller"
    assert {
        signal.name
        for signal in model.signals
        if signal.direction is not Direction.PARAMETER
    } == {
        "input.measured",
        "input.reference",
        "input.mode",
        "input.enabled",
        "input.weights[0]",
        "input.weights[1]",
        "input.weights[2]",
        "output.command",
        "output.effort",
        "output.phase",
        "output.active",
        "output.limits[0]",
        "output.limits[1]",
    }


def test_generate_one_unit_names_the_model_after_the_unit(tmp_path):
    architecture = _system_architecture()
    model, target = _generate_unit(architecture, "SensorLink", tmp_path / "one")

    document = (target / "SensorLink" / "modelDescription.xml").read_text(
        encoding="utf-8"
    )
    payload = load_adapter_model(target)

    assert model.name == "SensorLink"
    assert model.interface == "SensorLink"
    assert 'modelName="SensorLink"' in document
    assert payload["model_name"] == "SensorLink"
    assert {
        item["name"] for item in payload["signals"] if item["field"] is not None
    } == {
        "request.sample_rate",
        "request.channel",
        "request.trigger",
        "request.offsets[0]",
        "request.offsets[1]",
        "reading.measurement",
        "reading.count",
        "reading.valid",
        "reading.window[0]",
        "reading.window[1]",
        "reading.window[2]",
        "reading.window[3]",
    }


def test_generate_all_units_writes_one_model_per_unit(tmp_path):
    architecture = _system_architecture()
    destinations = []

    for unit in _SYSTEM_UNITS:
        _, target = _generate_unit(architecture, unit, tmp_path / unit)
        destination = target / unit / "modelDescription.xml"
        assert destination.is_file()
        assert f'modelName="{unit}"' in destination.read_text(encoding="utf-8")
        destinations.append(destination.parent.name)

    assert destinations == _SYSTEM_UNITS
    assert sorted(path.name for path in tmp_path.iterdir()) == _SYSTEM_UNITS
