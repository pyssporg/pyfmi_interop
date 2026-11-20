"""An out-of-tree serialization backend owns its payload and CMake additions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pyfmi_interop.codegen import generate_model
from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
    deterministic_guid,
)
from pyfmi_interop.serialization import register
from pyfmi_interop.serialization.base import Serialization, write_files
from pyfmi_interop.serialization.descriptor import WIRE_JSON_NAME, wire_json_bytes

pytestmark = pytest.mark.component


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s", initial=1.5),
        Signal("setpoint", 5, DataType.REAL, Direction.INPUT, rate_hz=50.0),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    rate_groups = (RateGroup("fast", 0.02, 0.01, ("setpoint",)),)
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        rate_groups=rate_groups,
        description="codegen fixture",
    )


class ExternalSerialization(Serialization):
    """A backend with its own proto file, codec, and CMake inputs."""

    name = "external_probe"
    format_id = 7

    def __init__(self, proto: Path, include_dir: Path) -> None:
        self.proto = proto
        self.include_dir = include_dir

    def payload_message(self, model: ModelDefinition) -> str:
        return "external_probe.Payload"

    def proto_package(self, model: ModelDefinition) -> str | None:
        return "external_probe.payload"

    def schema_files(self, model: ModelDefinition) -> dict[str, bytes]:
        # An external path is a valid key; emit_schema leaves the file in place.
        return {
            str(self.proto): self.proto.read_bytes(),
            WIRE_JSON_NAME: wire_json_bytes(
                model, serialization=self.name, format_id=self.format_id
            ),
        }

    def generate_codec(
        self, model: ModelDefinition, out: str | Path, role: str
    ) -> list[Path]:
        return write_files(out, {"model_wire.cpp": "// external codec\n"})

    def cmake_proto_sources(self, model: ModelDefinition) -> tuple[str, ...]:
        return (str(self.proto),)

    def cmake_proto_import_roots(self, model: ModelDefinition) -> tuple[str, ...]:
        return (str(self.proto.parent),)

    def cmake_include_dirs(self, model: ModelDefinition) -> tuple[str, ...]:
        return (str(self.include_dir),)

    def cmake_link_libraries(self, model: ModelDefinition) -> tuple[str, ...]:
        return ("protobuf::libprotobuf",)


@pytest.fixture
def backend(tmp_path):
    proto = tmp_path / "schema" / "external_payload.proto"
    proto.parent.mkdir(parents=True)
    proto.write_text(
        'syntax = "proto3";\n'
        "package external_probe.payload;\n"
        "message Payload { double value = 1; }\n",
        encoding="utf-8",
    )
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    instance = ExternalSerialization(proto, include_dir)
    register(instance)
    yield instance
    from pyfmi_interop.serialization import registry

    registry._BACKENDS.pop(instance.name, None)


def test_registry_accepts_any_registered_backend(tmp_path, backend):
    target = generate_model(make_model(), tmp_path / "gen", serialization=backend.name)

    assert target == tmp_path / "gen"
    assert (target / "model_wire.cpp").is_file()
    source = (target / "model_runtime.cpp").read_text(encoding="utf-8")
    assert (
        "static_cast<pyfmi_interop::wire::PayloadFormat>(7u)"
        in source
    )


def test_payload_identity_reaches_wire_json(tmp_path, backend):
    target = generate_model(make_model(), tmp_path / "gen", serialization=backend.name)
    payload = json.loads((target / "wire.json").read_text(encoding="utf-8"))

    assert payload["format"] == backend.name
    assert payload["format_id"] == backend.format_id
    assert payload["payload_message"] == "external_probe.Payload"
    assert payload["proto_package"] == "external_probe.payload"


def test_declared_cmake_additions_reach_cmakelists(tmp_path, backend):
    target = generate_model(make_model(), tmp_path / "gen", serialization=backend.name)
    cmake = (target / "CMakeLists.txt").read_text(encoding="utf-8")

    assert str(backend.proto) in cmake
    assert str(backend.proto.parent) in cmake
    assert str(backend.include_dir) in cmake
    assert "protobuf::libprotobuf" in cmake
    assert "model_wire.cpp" in cmake
    assert "IMPORT_ROOTS" in cmake


def test_schema_files_may_point_outside_the_generated_tree(tmp_path, backend):
    target = generate_model(make_model(), tmp_path / "gen", serialization=backend.name)

    assert not (target / "external_payload.proto").exists()
    assert backend.proto.is_file()
    assert 'package external_probe.payload;' in backend.proto.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["protobuf", "packed"])
def test_builtin_cmake_and_wire_json_match_golden(tmp_path, name):
    golden = Path(__file__).resolve().parent / "golden"
    target = generate_model(make_model(), tmp_path / name, serialization=name)

    assert (
        (target / "CMakeLists.txt").read_bytes()
        == (golden / f"demo_model.{name}.CMakeLists.txt").read_bytes()
    )
    wire_golden = (
        "demo_model.wire.json" if name == "protobuf" else f"demo_model.{name}.wire.json"
    )
    assert (
        wire_json_bytes(
            make_model(),
            serialization=name,
            format_id={"protobuf": 1, "packed": 2}[name],
        )
        == (golden / wire_golden).read_bytes()
    )


_CMAKE = shutil.which("cmake")
_CPP = shutil.which("g++") or shutil.which("c++")
_PROTOC = shutil.which("protoc")


@pytest.mark.cpp
@pytest.mark.skipif(_CMAKE is None, reason="cmake is not available")
@pytest.mark.skipif(_CPP is None, reason="no C++ compiler is available")
@pytest.mark.skipif(_PROTOC is None, reason="protoc is not available")
def test_declared_additions_compile_a_minimal_target(tmp_path, backend):
    source_dir = tmp_path / "probe"
    source_dir.mkdir()
    (source_dir / "probe.cpp").write_text(
        '#include "external_header.hpp"\n'
        '#include "external_payload.pb.h"\n'
        "int probe_function() {\n"
        "    external_probe::payload::Payload payload;\n"
        "    payload.set_value(1.0);\n"
        "    return external_probe_header();\n"
        "}\n",
        encoding="utf-8",
    )
    (backend.include_dir / "external_header.hpp").write_text(
        "inline int external_probe_header() { return 1; }\n", encoding="utf-8"
    )
    repo = Path(__file__).resolve().parents[1]
    proto_args = " ".join(f'"{path}"' for path in backend.cmake_proto_sources(make_model()))
    root_args = " ".join(
        f'"{path}"' for path in backend.cmake_proto_import_roots(make_model())
    )
    include_args = "\n    ".join(
        f'"{path}"' for path in backend.cmake_include_dirs(make_model())
    )
    link_args = " ".join(
        f'"{path}"' for path in backend.cmake_link_libraries(make_model())
    )
    (source_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(external_probe LANGUAGES CXX)\n"
        "set(CMAKE_CXX_STANDARD 17)\n"
        "set(CMAKE_CXX_STANDARD_REQUIRED ON)\n"
        f'include("{repo / "cmake" / "wire.cmake"}")\n'
        "find_package(Protobuf REQUIRED)\n"
        "add_library(external_probe STATIC probe.cpp)\n"
        "target_include_directories(\n"
        "    external_probe\n"
        "    PRIVATE\n"
        f"    {include_args}\n"
        ")\n"
        f"pyfmi_interop_wire_add_proto(external_probe {proto_args} IMPORT_ROOTS {root_args})\n"
        f"target_link_libraries(external_probe PRIVATE {link_args})\n",
        encoding="utf-8",
    )

    build = tmp_path / "build"
    subprocess.run(
        [_CMAKE, "-S", str(source_dir), "-B", str(build)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [_CMAKE, "--build", str(build)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (build / "libexternal_probe.a").is_file()
