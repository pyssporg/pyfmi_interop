"""Timing derivation and validation for the realtime execution IR.

Rate groups are inferred from :attr:`pyfmi_interop.ir.Signal.rate_hz`.
Signals without a rate run every scheduler step and form the ``base`` group at
the model step size.  Every other distinct rate becomes ``rate_<hz>hz`` with a
deadline of 80 % of its period; the name is derived from the frequency so two
runs over the same IR produce the same groups.

The IR stores periods in seconds, so frequencies are converted at the boundary.
"""

from __future__ import annotations

import math

from . import ir

__all__ = [
    "infer_rate_groups",
    "validate_timing",
    "frequency_to_period",
    "period_to_frequency",
]

#: Fraction of the period a rate group must finish within.
DEADLINE_FRACTION = 0.8

_RELATIVE_TOLERANCE = 1e-9


def frequency_to_period(hz: float) -> float:
    """Seconds per sample for a positive frequency in Hz."""

    return 1.0 / _positive(hz, "frequency")


def period_to_frequency(period_s: float) -> float:
    """Frequency in Hz for a positive period in seconds."""

    return 1.0 / _positive(period_s, "period")


def infer_rate_groups(model: ir.ModelDefinition) -> tuple[ir.RateGroup, ...]:
    """Group ``model`` signals by rate into deterministic rate groups.

    Signals with ``rate_hz is None`` form ``base`` at ``model.step_size_s``.
    Signals are sorted by name inside each group and groups are ordered base
    first, then slowest to fastest.
    """

    base: list[str] = []
    periods: dict[float, list[str]] = {}
    for signal in model.signals:
        if signal.rate_hz is None:
            base.append(signal.name)
        else:
            period = round(1.0 / signal.rate_hz, 12)
            periods.setdefault(period, []).append(signal.name)

    groups: list[ir.RateGroup] = []
    if base:
        groups.append(_group("base", model.step_size_s, base))
    for period in sorted(periods, reverse=True):
        groups.append(_group(_rate_name(1.0 / period), period, periods[period]))
    return tuple(groups)


def validate_timing(model: ir.ModelDefinition) -> None:
    """Raise :class:`ValueError` unless the timing plan is executable.

    On top of :meth:`pyfmi_interop.ir.ModelDefinition.validate`, every
    grouped signal must run at its group's period, and a signal without a rate
    must sit in the base group.
    """

    model.validate()

    names = [group.name for group in model.rate_groups]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate rate group names: {', '.join(duplicates)}")

    grouped: dict[str, ir.RateGroup] = {}
    for group in model.rate_groups:
        for signal_name in group.signals:
            grouped[signal_name] = group

    for signal in model.signals:
        group = grouped.get(signal.name)
        if group is None:
            continue
        if signal.rate_hz is None:
            if not _close(group.period_s, model.step_size_s):
                raise ValueError(
                    f"{signal.name}: signal without a rate must run at the base "
                    f"step {model.step_size_s}s, not {group.period_s}s"
                )
            continue
        expected = 1.0 / signal.rate_hz
        if not _close(group.period_s, expected):
            raise ValueError(
                f"{signal.name}: rate {signal.rate_hz} Hz needs period "
                f"{expected}s, but group {group.name!r} runs at {group.period_s}s"
            )


def _group(name: str, period_s: float, signals: list[str]) -> ir.RateGroup:
    return ir.RateGroup(
        name=name,
        period_s=period_s,
        deadline_s=DEADLINE_FRACTION * period_s,
        signals=tuple(sorted(signals)),
    )


def _rate_name(hz: float) -> str:
    if hz.is_integer():
        text = str(int(hz))
    else:
        text = f"{hz:.12g}".replace(".", "p").replace("-", "m").replace("+", "")
    return f"rate_{text}hz"


def _close(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 1e-12)
    return abs(left - right) <= _RELATIVE_TOLERANCE * scale


def _positive(value: float, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number, got {value!r}") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and > 0, got {number!r}")
    return number
