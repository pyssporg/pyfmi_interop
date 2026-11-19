"""Timing layer: rate grouping, conversion, and validation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pyfmi_interop import ir, timing

pytestmark = pytest.mark.unit


def _signal(
    name: str,
    rate_hz: float | None = None,
    *,
    value_reference: int = 0,
) -> ir.Signal:
    return ir.Signal(
        name=name,
        value_reference=value_reference,
        data_type=ir.DataType.REAL,
        direction=ir.Direction.OUTPUT,
        rate_hz=rate_hz,
    )


def _model(
    signals: list[ir.Signal],
    *,
    step_size_s: float = 0.001,
    rate_groups: tuple[ir.RateGroup, ...] = (),
) -> ir.ModelDefinition:
    return ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=step_size_s,
        signals=tuple(signals),
        rate_groups=rate_groups,
    )


@pytest.mark.parametrize("hz", [1.0, 2.0, 0.5, 10.0, 1000.0])
def test_frequency_period_round_trip(hz: float) -> None:
    period = timing.frequency_to_period(hz)
    assert period == pytest.approx(1.0 / hz)
    assert timing.period_to_frequency(period) == pytest.approx(hz)


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_frequency_and_period_reject_non_positive_or_non_finite(value: float) -> None:
    with pytest.raises(ValueError):
        timing.frequency_to_period(value)
    with pytest.raises(ValueError):
        timing.period_to_frequency(value)


def test_infer_rate_groups_is_deterministic_and_deadline_is_80_percent() -> None:
    model = _model(
        [
            _signal("fast", None, value_reference=0),
            _signal("also_fast", None, value_reference=1),
            _signal("one_hz", 1.0, value_reference=2),
            _signal("ten_b", 10.0, value_reference=3),
            _signal("ten_a", 10.0, value_reference=4),
            _signal("half_hz", 0.5, value_reference=5),
        ]
    )

    groups = timing.infer_rate_groups(model)

    assert [group.name for group in groups] == [
        "base",
        "rate_0p5hz",
        "rate_1hz",
        "rate_10hz",
    ]
    base, half, one, ten = groups
    assert base.period_s == pytest.approx(0.001)
    assert base.signals == ("also_fast", "fast")
    assert half.period_s == pytest.approx(2.0)
    assert one.period_s == pytest.approx(1.0)
    assert ten.period_s == pytest.approx(0.1)
    assert ten.signals == ("ten_a", "ten_b")
    for group in groups:
        assert group.deadline_s == pytest.approx(0.8 * group.period_s)


def test_infer_rate_groups_omits_base_when_every_signal_has_a_rate() -> None:
    model = _model([_signal("ten", 10.0)])

    groups = timing.infer_rate_groups(model)

    assert [group.name for group in groups] == ["rate_10hz"]


def test_inferred_groups_pass_model_and_timing_validation() -> None:
    model = _model(
        [
            _signal("fast", None, value_reference=0),
            _signal("one_hz", 1.0, value_reference=1),
            _signal("ten_hz", 10.0, value_reference=2),
        ],
        step_size_s=0.001,
    )

    validated = replace(model, rate_groups=timing.infer_rate_groups(model))

    timing.validate_timing(validated)


def test_aligned_rates_pass_and_unaligned_rates_are_rejected() -> None:
    aligned = _model([_signal("ten", 10.0)], step_size_s=0.001)
    timing.validate_timing(aligned)

    unaligned = _model([_signal("three", 3.0)], step_size_s=0.001)
    with pytest.raises(ValueError, match="does not align"):
        unaligned.validate()
    with pytest.raises(ValueError, match="does not align"):
        timing.validate_timing(unaligned)


def test_rate_group_constructor_rejects_invalid_period_and_deadline() -> None:
    with pytest.raises(ValueError, match="period_s must be > 0"):
        ir.RateGroup(name="bad", period_s=0.0, deadline_s=0.0)
    with pytest.raises(ValueError, match="deadline_s must not exceed period_s"):
        ir.RateGroup(name="bad", period_s=0.1, deadline_s=0.2)


def test_validate_timing_rejects_signal_rate_that_disagrees_with_its_group() -> None:
    group = ir.RateGroup(name="slow", period_s=0.5, deadline_s=0.4, signals=("one",))
    model = _model([_signal("one", 1.0)], rate_groups=(group,))

    with pytest.raises(ValueError, match="needs period"):
        timing.validate_timing(model)


def test_validate_timing_rejects_rate_less_signal_in_a_slow_group() -> None:
    group = ir.RateGroup(name="slow", period_s=0.1, deadline_s=0.08, signals=("fast",))
    model = _model([_signal("fast", None)], rate_groups=(group,))

    with pytest.raises(ValueError, match="without a rate"):
        timing.validate_timing(model)


def test_validate_timing_rejects_duplicate_group_names() -> None:
    first = ir.RateGroup(name="dup", period_s=0.1, deadline_s=0.08, signals=("a",))
    second = ir.RateGroup(name="dup", period_s=0.1, deadline_s=0.08, signals=("b",))
    model = _model(
        [_signal("a", None, value_reference=0), _signal("b", None, value_reference=1)],
        rate_groups=(first, second),
    )

    with pytest.raises(ValueError, match="duplicate rate group names"):
        timing.validate_timing(model)
