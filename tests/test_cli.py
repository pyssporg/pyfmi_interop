from __future__ import annotations

from pathlib import Path

from pyfmi_interop import cli
from pyfmi_interop.codegen import generate_model
from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
    deterministic_guid,
    write_model_json,
)


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s"),
        Signal("setpoint", 2, DataType.REAL, Direction.INPUT, rate_hz=50.0),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        rate_groups=(RateGroup("fast", 0.02, 0.01, ("setpoint",)),),
        description="cli fixture",
    )


def write_fixture(tmp_path) -> Path:
    path = tmp_path / "model.json"
    write_model_json(make_model(), path)
    return path


def test_transports_table_lists_only_shipped_transports(capsys):
    assert cli.main(["transports"]) == 0
    output = capsys.readouterr().out

    assert "name" in output
    assert set(output.split()[1:]) == {"loopback", "udp", "tcp"}


def test_serializations_table_lists_the_backends(capsys):
    assert cli.main(["serializations"]) == 0
    output = capsys.readouterr().out

    assert "name" in output
    assert set(output.split()[1:]) == {"protobuf", "packed", "opaque"}


def test_inspect_model_json(tmp_path, capsys):
    path = write_fixture(tmp_path)

    assert cli.main(["inspect", "--model-json", str(path)]) == 0
    output = capsys.readouterr().out

    assert "model: demo_model" in output
    assert "signals: 2" in output
    assert "1: speed (real, output, unit=m/s)" in output
    assert "2: setpoint (real, input, rate_hz=50.0)" in output
    assert "rate_groups: 1" in output


def test_generate_from_model_json(tmp_path, capsys):
    path = write_fixture(tmp_path)
    out_dir = tmp_path / "generated"

    assert cli.main(["generate", "--model-json", str(path), "--out", str(out_dir)]) == 0
    assert "Generated model sources at" in capsys.readouterr().out
    assert (out_dir / "model_runtime.cpp").is_file()
    assert (out_dir / "CMakeLists.txt").is_file()
    assert (out_dir / "model.json").is_file()


def test_generate_with_an_explicit_serialization(tmp_path, capsys):
    path = write_fixture(tmp_path)
    out_dir = tmp_path / "packed"

    assert (
        cli.main(
            [
                "generate",
                "--model-json",
                str(path),
                "--out",
                str(out_dir),
                "--serialization",
                "packed",
            ]
        )
        == 0
    )
    assert "Generated model sources at" in capsys.readouterr().out
    assert not (out_dir / "demo_model.proto").exists()
    assert '"format": "packed"' in (out_dir / "wire.json").read_text(encoding="utf-8")


def test_missing_model_json_is_an_error(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    assert cli.main(["inspect", "--model-json", str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "missing.json" in captured.err


def test_package_command(tmp_path, capsys):
    model_dir = generate_model(make_model(), tmp_path / "gen")
    library = tmp_path / "libdemo_model.so"
    library.write_bytes(b"fake shared library")
    destination = tmp_path / "demo.fmu"

    code = cli.main(
        [
            "package",
            str(model_dir),
            "--library",
            str(library),
            "--out",
            str(destination),
        ]
    )

    assert code == 0
    assert "Packaged" in capsys.readouterr().out
    assert destination.is_file()


def test_schema_command_writes_both_artifacts(tmp_path, capsys):
    path = write_fixture(tmp_path)
    out_dir = tmp_path / "schema"

    assert cli.main(["schema", "--model-json", str(path), "--out", str(out_dir)]) == 0
    output = capsys.readouterr().out

    proto_path = out_dir / "demo_model.proto"
    descriptor_path = out_dir / "wire.json"
    assert proto_path.is_file()
    assert descriptor_path.is_file()
    assert f"Schema proto at {proto_path}" in output
    assert f"Schema descriptor at {descriptor_path}" in output
    assert "package pyfmi_interop.wire;" in proto_path.read_text(encoding="utf-8")
    assert '"model": "demo_model"' in descriptor_path.read_text(encoding="utf-8")


def test_help_lists_the_commands():
    help_text = cli.build_parser().format_help()

    for command in (
        "transports",
        "serializations",
        "inspect",
        "generate",
        "build",
        "package",
        "schema",
    ):
        assert command in help_text
