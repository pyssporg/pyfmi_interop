"""The public specification contract: identity, projection, validation."""

from __future__ import annotations

import pytest

from pyfmi_interop import BuildConfig, ModelSpec, generate_model
from pyfmi_interop.ir import DataType, Direction, Signal, deterministic_guid


def _spec(**overrides) -> ModelSpec:
    fields = {
        "name": "demo",
        "signals": (
            Signal("speed", 1, DataType.REAL, Direction.OUTPUT, rate_hz=1000.0),
        ),
        "step_size_s": 0.001,
        "realtime": True,
    }
    fields.update(overrides)
    return ModelSpec(**fields)  # type: ignore[arg-type]


def test_guid_defaults_to_the_deterministic_name_derivative():
    assert _spec().guid == deterministic_guid("demo")


def test_to_model_carries_role_and_serialization_from_the_config():
    config = BuildConfig(serialization="packed", role="receiver")

    model = _spec().to_model(config)

    assert model.role == "receiver"
    assert model.serialization == "packed"
    assert model.guid == deterministic_guid("demo")
    assert model.name == "demo"
    assert model.step_size_s == 0.001


def test_empty_name_is_rejected_by_validation():
    with pytest.raises(ValueError, match="model name must not be empty"):
        _spec(name="").validate()


def test_realtime_model_without_a_step_is_rejected():
    with pytest.raises(ValueError, match="realtime models require step_size_s"):
        _spec(step_size_s=None).validate()


def test_non_realtime_model_needs_no_step():
    spec = _spec(step_size_s=None, realtime=False)

    model = spec.to_model()

    assert model.step_size_s is None
    assert model.realtime is False


def test_spec_and_its_projection_generate_byte_identical_trees(tmp_path):
    config = BuildConfig(serialization="packed", role="receiver")
    spec = _spec()

    from_spec = generate_model(spec, tmp_path / "spec", config)
    from_model = generate_model(spec.to_model(config), tmp_path / "model")

    names = sorted(path.name for path in from_spec.iterdir() if path.is_file())
    assert names
    for name in names:
        assert (from_spec / name).read_bytes() == (from_model / name).read_bytes(), name
