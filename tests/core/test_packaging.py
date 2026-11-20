from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from zipfile import ZipFile

import pytest

from pyfmi_interop import native
from pyfmi_interop.codegen import generate_model
from pyfmi_interop.core import BuildConfig
from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    ProjectionError,
    RateGroup,
    Signal,
    deterministic_guid,
)
from pyfmi_interop.packaging import (
    package_fmu,
    platform_binary_dir,
    platform_library_extension,
)
from pyfmi_interop.schema import render_proto, render_wire_json


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s", initial=1.5),
        Signal("setpoint", 5, DataType.REAL, Direction.INPUT, rate_hz=50.0),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        rate_groups=(RateGroup("fast", 0.02, 0.01, ("setpoint",)),),
        description="packaging fixture",
    )


def package_fixture(tmp_path, name: str = "demo.fmu"):
    model_dir = generate_model(make_model(), tmp_path / "gen")
    library = tmp_path / "libdemo_model.so"
    library.write_bytes(b"\x7fELF fake runtime")
    destination = package_fmu(model_dir, library, tmp_path / name)
    return model_dir, destination


def test_archive_layout_is_sorted_and_self_describing(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        names = archive.namelist()

    assert names == sorted(names)
    expected_binary = (
        f"binaries/{platform_binary_dir()}/demo_model{platform_library_extension()}"
    )
    assert set(names) == {
        "modelDescription.xml",
        "resources/model.json",
        "resources/runtime.json",
        "resources/transport.json",
        expected_binary,
        f"binaries/{platform_binary_dir()}/demo_model.proto",
        f"binaries/{platform_binary_dir()}/wire.json",
    }
    assert expected_binary.startswith("binaries/")
    assert expected_binary.endswith(platform_library_extension())


def test_schema_bundle_lands_next_to_the_binary(tmp_path):
    model = make_model()
    model_dir, destination = package_fixture(tmp_path)
    platform = platform_binary_dir()

    with ZipFile(destination) as archive:
        proto = archive.read(f"binaries/{platform}/demo_model.proto").decode("utf-8")
        descriptor = archive.read(f"binaries/{platform}/wire.json").decode("utf-8")

    assert proto == render_proto(model)
    assert descriptor == render_wire_json(model)
    assert (model_dir / "model.json").is_file()


def test_non_projectable_signal_fails_packaging_without_writing_a_fmu(tmp_path):
    model = ModelDefinition(
        name="bad_model",
        guid=deterministic_guid("bad_model"),
        step_size_s=0.01,
        signals=(Signal("bad\x00name", 1, DataType.REAL, Direction.OUTPUT),),
    )
    model_dir = tmp_path / "gen"
    model_dir.mkdir()
    library = tmp_path / "libbad_model.so"
    library.write_bytes(b"fake")
    destination = tmp_path / "bad.fmu"

    with pytest.raises(ProjectionError):
        package_fmu(model_dir, library, destination, model=model)
    assert not destination.exists()


def test_packaging_is_byte_deterministic(tmp_path):
    _, first = package_fixture(tmp_path, "first.fmu")
    _, second = package_fixture(tmp_path, "second.fmu")

    assert first.read_bytes() == second.read_bytes()


def test_model_description_is_valid_fmi2(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        document = archive.read("modelDescription.xml")

    root = ET.fromstring(document)
    assert root.tag == "fmiModelDescription"
    assert root.attrib["fmiVersion"] == "2.0"
    assert root.attrib["modelName"] == "demo_model"
    assert root.attrib["guid"] == deterministic_guid("demo_model")
    assert len(root.findall("CoSimulation")) == 1

    variables = {
        variable.attrib["name"]: variable
        for variable in root.findall("./ModelVariables/ScalarVariable")
    }
    assert set(variables) == {"speed", "setpoint", "label", "enable", "mode"}
    assert variables["speed"].attrib["causality"] == "output"
    assert variables["speed"].attrib["variability"] == "continuous"
    assert variables["speed"].attrib["valueReference"] == "1"
    assert variables["speed"].find("Real").attrib == {"unit": "m/s", "start": "1.5"}
    assert variables["setpoint"].attrib["causality"] == "input"
    assert variables["label"].find("String").attrib["start"] == "hi"
    assert variables["enable"].attrib["causality"] == "parameter"
    assert variables["enable"].attrib["variability"] == "fixed"
    assert variables["enable"].find("Boolean").attrib["start"] == "true"
    assert variables["mode"].attrib["causality"] == "parameter"
    assert variables["mode"].attrib["variability"] == "fixed"
    assert variables["mode"].find("Integer").attrib["start"] == "2"

    experiment = root.find("DefaultExperiment")
    assert experiment is not None
    assert experiment.attrib["stepSize"] == "0.01"

    outputs = root.findall("./ModelStructure/Outputs/Unknown")
    assert [item.attrib["index"] for item in outputs] == ["1", "2"]


def test_adapter_description_has_no_default_experiment(tmp_path):
    adapter = replace(make_model(), realtime=False, step_size_s=None)
    model_dir = generate_model(adapter, tmp_path / "adapter")
    library = tmp_path / "libdemo_model.so"
    library.write_bytes(b"\x7fELF fake adapter")
    destination = package_fmu(
        model_dir, library, tmp_path / "adapter.fmu", model=adapter
    )

    with ZipFile(destination) as archive:
        root = ET.fromstring(archive.read("modelDescription.xml"))

    assert root.find("DefaultExperiment") is None


def test_packaged_parameter_block_is_fixed_and_carries_authored_starts(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        root = ET.fromstring(archive.read("modelDescription.xml"))

    variables = {
        variable.attrib["name"]: variable
        for variable in root.findall("./ModelVariables/ScalarVariable")
        if variable.attrib["causality"] == "parameter"
    }
    assert set(variables) == {"enable", "mode"}
    for variable in variables.values():
        assert variable.attrib["variability"] == "fixed"
    assert variables["enable"].find("Boolean").attrib["start"] == "true"
    assert variables["mode"].find("Integer").attrib["start"] == "2"


def test_runtime_and_model_resources(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        runtime = json.loads(archive.read("resources/runtime.json"))
        model = json.loads(archive.read("resources/model.json"))

    assert runtime["modelIdentifier"] == "demo_model"
    assert runtime["platform"] == platform_binary_dir()
    assert runtime["binary"].endswith(f"demo_model{platform_library_extension()}")
    assert runtime["serialization"] == "protobuf"
    assert runtime["format_id"] == 1
    assert "adapters" not in runtime
    assert model["name"] == "demo_model"


def test_transport_json_documents_the_parameter_contract(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        transport = json.loads(archive.read("resources/transport.json"))

    assert transport["default"] == "loopback"
    assert transport["schemes"] == ["loopback", "udp", "tcp"]
    assert transport["parameter_keys"] == [
        "transport",
        "bind_address",
        "peer_address",
        "queue_depth",
        "deadline_s",
    ]
    assert transport["env"] == "PYFMI_INTEROP_TRANSPORT"
    assert "no parameter interface" in transport["env_fallback"]
    assert transport["uri_examples"]


def test_packed_and_opaque_fmus_ship_only_their_own_schema(tmp_path):
    for name, format_id in (("packed", 2), ("opaque", 0)):
        model = make_model()
        model = replace(model, serialization=name, role="adapter")
        model_dir = generate_model(
            model, tmp_path / f"gen-{name}", BuildConfig(serialization=name)
        )
        library = tmp_path / f"libdemo_model_{name}.so"
        library.write_bytes(b"fake")
        destination = package_fmu(
            model_dir, library, tmp_path / f"{name}.fmu", model=model
        )

        with ZipFile(destination) as archive:
            names = archive.namelist()
            runtime = json.loads(archive.read("resources/runtime.json"))

        platform = platform_binary_dir()
        assert f"binaries/{platform}/wire.json" in names
        assert f"binaries/{platform}/demo_model.proto" not in names
        assert runtime["serialization"] == name
        assert runtime["format_id"] == format_id


def test_missing_library_is_rejected(tmp_path):
    model_dir = generate_model(make_model(), tmp_path / "gen")

    with pytest.raises(FileNotFoundError, match="shared library"):
        package_fmu(model_dir, tmp_path / "missing.so", tmp_path / "demo.fmu")


def test_missing_model_json_is_rejected(tmp_path):
    model_dir = tmp_path / "empty"
    model_dir.mkdir()
    library = tmp_path / "libdemo_model.so"
    library.write_bytes(b"fake")

    with pytest.raises(FileNotFoundError, match="model.json"):
        package_fmu(model_dir, library, tmp_path / "demo.fmu")


def test_native_cmake_module_prefers_source_tree(tmp_path):
    source = tmp_path / "repo"
    (source / "cmake").mkdir(parents=True)
    (source / "cmake" / "wire.cmake").write_text("# bundled wire\n", encoding="utf-8")

    assert native.cmake_module_dir(source) == source / "cmake"


def test_bundled_cmake_dir_lives_under_the_runtime_package():
    bundled = native.bundled_cmake_dir()

    assert bundled.name == "cmake"
    assert bundled.parent.name == "_runtime"


_SUPPORTED = sys.platform.startswith("linux") or sys.platform in {"darwin", "win32"}


@pytest.mark.skipif(not _SUPPORTED, reason="unsupported platform")
def test_platform_directory_matches_host():
    assert platform_binary_dir() in {"linux64", "darwin64", "win64"}
    assert platform_library_extension() in {".so", ".dylib", ".dll"}
