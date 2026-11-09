from __future__ import annotations

from pathlib import Path

from pyfmi_distributed import cli
from pyfmi_distributed.codegen import generate_model
from pyfmi_distributed.ir import (
    DataType,
    Direction,
    ModelDefinition,
    RateGroup,
    Signal,
    TransportBinding,
    deterministic_guid,
    write_model_json,
)


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s"),
        Signal("setpoint", 0, DataType.REAL, Direction.INPUT, rate_hz=50.0),
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
        description="cli fixture",
    )


def write_fixture(tmp_path) -> Path:
    path = tmp_path / "model.json"
    write_model_json(make_model(), path)
    return path


def test_adapters_table(capsys):
    assert cli.main(["adapters"]) == 0
    output = capsys.readouterr().out

    assert "name" in output
    assert "kind" in output
    assert "available" in output
    assert "experimental" in output
    assert "requires" in output
    for adapter in ("loopback", "hla", "dis", "dcp", "ros2", "ed247"):
        assert adapter in output
    assert "yes" in output


def test_inspect_model_json(tmp_path, capsys):
    path = write_fixture(tmp_path)

    assert cli.main(["inspect", "--model-json", str(path)]) == 0
    output = capsys.readouterr().out

    assert "model: demo_model" in output
    assert "signals: 2" in output
    assert "1: speed (real, output, unit=m/s)" in output
    assert "0: setpoint (real, input, rate_hz=50.0)" in output
    assert "bindings: 2" in output
    assert "rate_groups: 1" in output


def test_generate_from_model_json(tmp_path, capsys):
    path = write_fixture(tmp_path)
    out_dir = tmp_path / "generated"

    assert cli.main(["generate", "--model-json", str(path), "--out", str(out_dir)]) == 0
    assert "Generated model sources at" in capsys.readouterr().out
    assert (out_dir / "model_runtime.cpp").is_file()
    assert (out_dir / "CMakeLists.txt").is_file()
    assert (out_dir / "model.json").is_file()


def test_missing_model_json_is_an_error(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    assert cli.main(["inspect", "--model-json", str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "missing.json" in captured.err


def test_sysml_generation_names_the_sysml_extra(tmp_path, capsys, monkeypatch):
    def missing_module(name: str):
        raise ImportError("simulated missing optional dependency")

    monkeypatch.setattr("pyfmi_distributed.__getattr__", missing_module)

    code = cli.main(
        [
            "generate",
            "--sysml",
            str(tmp_path / "architecture.sysml"),
            "--out",
            str(tmp_path / "generated"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "sysml" in captured.err
    assert "extra" in captured.err


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


def test_build_adapter_options_become_cmake_gates(monkeypatch, tmp_path, capsys):
    captured: dict[str, list[str]] = {}

    def fake_build_model(model_dir, build_dir=None, *, cmake_args=()):
        captured["cmake_args"] = list(cmake_args)
        return tmp_path / "libdemo_model.so"

    monkeypatch.setattr(cli, "build_model", fake_build_model)

    assert (
        cli.main(
            ["build", str(tmp_path), "--adapter", "hla", "--adapter", "dis"]
        )
        == 0
    )
    assert captured["cmake_args"] == [
        "-DPYFMI_DIST_ENABLE_DIS=ON",
        "-DPYFMI_DIST_ENABLE_HLA=ON",
    ]

    assert cli.main(["build", str(tmp_path)]) == 0
    assert captured["cmake_args"] == []


def test_build_rejects_unknown_adapter(monkeypatch, tmp_path, capsys):
    def unexpected_build_model(*args, **kwargs):
        raise AssertionError("build must not start for an unknown adapter")

    monkeypatch.setattr(cli, "build_model", unexpected_build_model)

    assert cli.main(["build", str(tmp_path), "--adapter", "bogus"]) == 1
    assert "unknown adapter" in capsys.readouterr().err


def test_help_lists_the_commands():
    help_text = cli.build_parser().format_help()

    for command in ("adapters", "inspect", "generate", "build", "package"):
        assert command in help_text
