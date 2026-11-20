"""One specification in, generated sources, a native library and an FMU out."""

from __future__ import annotations

import shutil
from zipfile import ZipFile

import pytest

from pyfmi_interop import ModelSpec, compile_model
from pyfmi_interop.ir import DataType, Direction, Signal

_CMAKE = shutil.which("cmake")


def _spec() -> ModelSpec:
    return ModelSpec(
        name="pipeline_demo",
        step_size_s=0.001,
        signals=(
            Signal("speed", 1, DataType.REAL, Direction.OUTPUT, rate_hz=1000.0),
        ),
    )


@pytest.mark.cpp
@pytest.mark.skipif(_CMAKE is None, reason="cmake is not available")
def test_compile_model_yields_sources_library_and_fmu(tmp_path):
    compiled = compile_model(_spec(), tmp_path / "model")

    assert compiled.sources.is_dir()
    assert (compiled.sources / "model.json").is_file()
    assert compiled.library.is_file()
    assert compiled.fmu.is_file()
    with ZipFile(compiled.fmu) as archive:
        assert "modelDescription.xml" in archive.namelist()


def test_single_parse_then_adapter_generation_never_reloads(tmp_path, monkeypatch):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    import pycps_sysml2

    from pyfmi_interop import sysml

    source = tmp_path / "single.sysml"
    source.write_text(
        "package Single {\n"
        "  private import ScalarValues::*;\n"
        "  port def Signal { attribute value : Real; }\n"
        "  part def FmuModel { }\n"
        "  part def FmuInterop :> FmuModel { }\n"
        "  part def Only :> FmuInterop { out port y : Signal; }\n"
        "}\n",
        encoding="utf-8",
    )

    calls = {"count": 0}
    real_load = pycps_sysml2.load

    def counted(*args, **kwargs):
        calls["count"] += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(pycps_sysml2, "load", counted)
    parsed = sysml.parse(source, name="OnlyModel", realtime=False)
    assert calls["count"] == 1

    def failing(*args, **kwargs):
        raise AssertionError("generate_adapter reloaded the SysML source")

    monkeypatch.setattr(pycps_sysml2, "load", failing)
    target = sysml.generate_adapter(parsed, tmp_path / "adapter")

    assert (target / "wire.json").is_file()
    assert (target / "CMakeLists.txt").is_file()
    with pytest.raises(AssertionError, match="reloaded"):
        sysml.parse(source, name="OnlyModel", realtime=False)
