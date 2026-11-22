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

