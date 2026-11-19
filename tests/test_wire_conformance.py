"""Python-to-C++ wire conformance: one generated model, one frame, two encoders."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pyfmi_interop import native, wire
from pyfmi_interop.builder import build_model
from pyfmi_interop.codegen import generate_model
from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    Signal,
    deterministic_guid,
)
from pyfmi_interop.schema import payload_message_name, proto_filename
from pyfmi_interop.serialization.naming import field_identifiers, wire_signals

pytestmark = [pytest.mark.cpp, pytest.mark.contract]

_INSTANCE = 7
_SEQUENCE = 42
_TIMESTAMP_NS = 1_700_000_000_000_000_000


def _make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, initial=1.5),
        Signal("setpoint", 5, DataType.REAL, Direction.INPUT),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
    )


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _python_payload(model: ModelDefinition, descriptor_path: Path) -> bytes:
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

    file_set = descriptor_pb2.FileDescriptorSet()
    file_set.ParseFromString(descriptor_path.read_bytes())
    pool = descriptor_pool.DescriptorPool()
    for file_proto in file_set.file:
        pool.Add(file_proto)

    descriptor = pool.FindMessageTypeByName(
        f"pyfmi_interop.wire.{payload_message_name(model)}"
    )
    message_class = message_factory.GetMessageClass(descriptor)
    message = message_class()
    fields = field_identifiers(model)

    for signal in sorted(
        wire_signals(model), key=lambda item: (item.value_reference, item.name)
    ):
        value = getattr(message, fields[signal.name])
        if signal.data_type is DataType.REAL:
            value.real = float(signal.initial or 0.0)
        elif signal.data_type is DataType.INTEGER:
            value.integer = int(signal.initial or 0)
        elif signal.data_type is DataType.BOOLEAN:
            value.boolean = _bool(signal.initial)
        else:
            value.string = str(signal.initial or "").encode("utf-8")

    return message.SerializeToString(deterministic=True)


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not available")
@pytest.mark.skipif(shutil.which("protoc") is None, reason="protoc is not available")
def test_generated_model_frame_matches_python(tmp_path):
    pytest.importorskip("google.protobuf")

    repo_root = Path(__file__).resolve().parents[1]
    library = native.bundled_library_path()
    if not library.is_file():
        library = native.default_runtime_library_path(repo_root)
    if not library.is_file():
        pytest.skip("native runtime library has not been built")
    includes = native.runtime_include_dirs(repo_root)
    if not includes:
        pytest.skip("native runtime headers are not available")

    model = _make_model()
    source = generate_model(model, tmp_path / "gen")
    build_dir = tmp_path / "build"
    build_model(
        source,
        build_dir,
        runtime_library=library,
        runtime_include=includes[0],
        cmake_args=["-DPYFMI_INTEROP_WIRE=protobuf"],
    )

    executables = sorted(build_dir.rglob("wire_conformance"))
    assert executables, "the generated project did not build wire_conformance"

    environment = dict(os.environ)
    library_path = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = (
        f"{build_dir}:{library_path}" if library_path else str(build_dir)
    )
    completed = subprocess.run(
        [str(executables[0])],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    cpp_frame_hex = completed.stdout.strip()

    descriptor_path = tmp_path / "payload.desc"
    subprocess.run(
        [
            "protoc",
            f"--descriptor_set_out={descriptor_path}",
            "--include_imports",
            f"-I{source}",
            str(source / proto_filename(model)),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = _python_payload(model, descriptor_path)
    python_frame_hex = wire.encode(
        model,
        payload,
        instance=_INSTANCE,
        sequence=_SEQUENCE,
        timestamp_ns=_TIMESTAMP_NS,
        payload_format=wire.PayloadFormat.PROTOBUF,
    ).hex()

    assert cpp_frame_hex == python_frame_hex


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not available")
def test_generated_packed_frame_matches_python(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    library = native.bundled_library_path()
    if not library.is_file():
        library = native.default_runtime_library_path(repo_root)
    if not library.is_file():
        pytest.skip("native runtime library has not been built")
    includes = native.runtime_include_dirs(repo_root)
    if not includes:
        pytest.skip("native runtime headers are not available")

    from pyfmi_interop.serialization import packed

    model = _make_model()
    source = generate_model(model, tmp_path / "gen", serialization="packed")
    build_dir = tmp_path / "build"
    build_model(
        source,
        build_dir,
        runtime_library=library,
        runtime_include=includes[0],
    )

    executables = sorted(build_dir.rglob("wire_conformance"))
    assert executables, "the generated project did not build wire_conformance"

    environment = dict(os.environ)
    library_path = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = (
        f"{build_dir}:{library_path}" if library_path else str(build_dir)
    )
    completed = subprocess.run(
        [str(executables[0])],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr

    payload = packed.encode(model)
    expected = wire.encode(
        model,
        payload,
        instance=_INSTANCE,
        sequence=_SEQUENCE,
        timestamp_ns=_TIMESTAMP_NS,
        payload_format=wire.PayloadFormat.PACKED,
    ).hex()

    assert completed.stdout.strip() == expected
