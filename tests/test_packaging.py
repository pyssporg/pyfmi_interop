from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import pytest

from pyfmi_interop import native
from pyfmi_interop.codegen import generate_model
from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
    TransportBinding,
    deterministic_guid,
)
from pyfmi_interop.packaging import (
    package_fmu,
    platform_binary_dir,
    platform_library_extension,
)


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s", initial=1.5),
        Signal("setpoint", 0, DataType.REAL, Direction.INPUT, rate_hz=50.0),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    bindings = (
        TransportBinding("speed", "hla", "Speed", Direction.OUTPUT),
        TransportBinding("setpoint", "dis", "Setpoint", Direction.INPUT),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        bindings=bindings,
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
        "resources/adapters.json",
        "resources/model.json",
        "resources/runtime.json",
        expected_binary,
    }
    assert expected_binary.startswith("binaries/")
    assert expected_binary.endswith(platform_library_extension())


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
    assert variables["enable"].find("Boolean").attrib["start"] == "true"
    assert variables["enable"].attrib["variability"] == "tunable"
    assert variables["mode"].find("Integer").attrib["start"] == "2"

    outputs = root.findall("./ModelStructure/Outputs/Unknown")
    assert [item.attrib["index"] for item in outputs] == ["2", "3"]


def test_runtime_and_adapters_resources(tmp_path):
    _, destination = package_fixture(tmp_path)

    with ZipFile(destination) as archive:
        runtime = json.loads(archive.read("resources/runtime.json"))
        adapters = json.loads(archive.read("resources/adapters.json"))
        model = json.loads(archive.read("resources/model.json"))

    assert runtime["modelIdentifier"] == "demo_model"
    assert runtime["platform"] == platform_binary_dir()
    assert runtime["binary"].endswith(f"demo_model{platform_library_extension()}")
    assert runtime["adapters"] == ["dis", "hla"]
    assert model["name"] == "demo_model"
    assert {item["name"] for item in adapters["adapters"]} == {
        "dcp",
        "dis",
        "ed247",
        "hla",
        "loopback",
        "ros2",
    }


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
    module = source / "cmake" / "adapters.cmake"
    module.write_text("# bundled adapter module\n", encoding="utf-8")

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
