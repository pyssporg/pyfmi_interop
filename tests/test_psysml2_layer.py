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

from pyfmi_interop import generate_model, package_fmu
from pyfmi_interop.packaging import platform_binary_dir
from pyfmi_interop.psysml2 import (
    load_adapter_model,
    wire_model_from_adapter_json,
)

pytestmark = [pytest.mark.cpp, pytest.mark.system]

_EXAMPLE = (
    Path(__file__).resolve().parents[1] / "examples" / "adapter" / "actuator_link.sysml"
)


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


def test_fmi_layer_requires_a_sysml_source(example, tmp_path):
    with pytest.raises(ValueError, match="source="):
        generate_model(example, tmp_path, fmi_layer="psysml2")


def test_tree_carries_both_namespaces_per_signal(example, tmp_path):
    target = _generate(example, tmp_path)
    wire = json.loads((target / "wire.json").read_text(encoding="utf-8"))
    model = load_adapter_model(target)

    assert wire["fmi_layer"] == "psysml2"
    assert {item["name"] for item in wire["parameters"]} == {
        "transport",
        "bind_address",
        "peer_address",
        "queue_depth",
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
    extended = original.replace(
        '    attribute queue_depth : Integer = 8;',
        '    attribute queue_depth : Integer = 8;\n'
        '    attribute protocol : String = "v1";',
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
    assert "protocol" in {item["name"] for item in wire_b["parameters"]}


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
    assert 'modelName="Root.ActuatorLink"' in document
    assert 'modelIdentifier="ActuatorLink"' in document
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
        "  part def ActuatorLink {",
        "  part def ActuatorLink {\n"
        "    attribute pyssp_step_size : Real = 0.002;",
    )
    rated_text = original.replace(
        "  port def Command {",
        "  port def Command {\n"
        "    attribute pyssp_rate : Real = 250.0;",
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
        "  part def Root {",
        "  part def Root {\n"
        "    attribute pyssp_default_start_time : Real = 0.0;\n"
        "    attribute pyssp_default_stop_time : Real = 1.0;",
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
        "  port def Command {\n"
        "    attribute pyssp_rate : Real = 250.0;",
    ).replace(
        "  port def Feedback {",
        "  port def Feedback {\n"
        "    attribute pyssp_rate : Real = 100.0;",
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


def _extension() -> str:
    from pyfmi_interop.packaging import platform_library_extension

    return platform_library_extension()
