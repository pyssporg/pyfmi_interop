"""Wire-projection contract of the realtime IR."""

from __future__ import annotations

import json

import pytest

from pyfmi_interop import ir

pytestmark = pytest.mark.unit


def _signal(name: str, value_reference: int = 1, **kwargs) -> ir.Signal:
    return ir.Signal(
        name,
        value_reference,
        kwargs.pop("data_type", ir.DataType.REAL),
        kwargs.pop("direction", ir.Direction.OUTPUT),
        **kwargs,
    )


def _model(*signals: ir.Signal) -> ir.ModelDefinition:
    return ir.ModelDefinition(
        name="demo",
        guid=ir.deterministic_guid("demo"),
        step_size_s=0.01,
        signals=tuple(signals),
    )


def test_enum_numbers_are_frozen_and_strings_are_unchanged() -> None:
    assert [(member.value, member.number) for member in ir.DataType] == [
        ("real", 1),
        ("integer", 2),
        ("boolean", 3),
        ("string", 4),
    ]
    assert [(member.value, member.number) for member in ir.Direction] == [
        ("input", 1),
        ("output", 2),
        ("parameter", 3),
    ]
    assert ir.DataType.REAL == "real"
    assert ir.Direction.OUTPUT == "output"
    assert ir.DataType.from_number(4) is ir.DataType.STRING
    assert ir.Direction.from_number(3) is ir.Direction.PARAMETER
    with pytest.raises(ValueError):
        ir.DataType.from_number(0)


def test_assign_value_references_starts_at_one_in_canonical_order() -> None:
    assigned = ir.assign_value_references(
        (_signal("b", 99), _signal("a", 42))
    )

    assert [signal.name for signal in assigned] == ["a", "b"]
    assert [signal.value_reference for signal in assigned] == [1, 2]
    _model(*assigned).validate()


@pytest.mark.parametrize("name", ["a.b", "a b", "a__b", "1a", "out.value[0]"])
def test_interface_names_are_carried_by_the_ir(name: str) -> None:
    # SysML/FMI names are interface names; the serialization backend maps them
    # to its own identifier.  The IR only rejects names that cannot be carried.
    _model(_signal(name)).validate()


@pytest.mark.parametrize("name", ["bad\x00name", "bad\nname"])
def test_names_with_control_characters_are_rejected(name: str) -> None:
    signal = _signal(name)
    with pytest.raises(ir.ProjectionError) as error:
        _model(signal).validate()
    assert error.value.signal_name == name


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ir.ProjectionError, match="must not be empty"):
        _signal("")


def test_zero_id_is_rejected_with_the_signal_name() -> None:
    with pytest.raises(ir.ProjectionError, match="value_reference 0 is reserved") as error:
        _signal("pending", 0)
    assert error.value.signal_name == "pending"


def test_duplicate_ids_are_rejected_with_the_second_signal_name() -> None:
    model = _model(_signal("first", 1), _signal("second", 1))

    with pytest.raises(ir.ProjectionError, match="duplicate value reference 1") as error:
        model.validate()
    assert error.value.signal_name == "second"


@pytest.mark.parametrize("value_reference", [-1, 536_870_912, 19_000, 19_999])
def test_illegal_field_numbers_are_rejected_at_construction(value_reference: int) -> None:
    with pytest.raises(ir.ProjectionError) as error:
        _signal("bad", value_reference)
    assert error.value.signal_name == "bad"


@pytest.mark.parametrize("value_reference", [1, 18_999, 20_000, 536_870_911])
def test_legal_field_numbers_are_accepted(value_reference: int) -> None:
    _signal("good", value_reference).check_projection()


def test_string_capacity_zero_is_rejected() -> None:
    with pytest.raises(ir.ProjectionError, match="positive capacity"):
        _signal("label", data_type=ir.DataType.STRING, capacity=0)


@pytest.mark.parametrize("initial", [5, True, b"bytes"])
def test_non_string_initial_for_string_signal_is_rejected(initial: object) -> None:
    with pytest.raises(ir.ProjectionError, match="initial value must be a str"):
        _signal(
            "label",
            data_type=ir.DataType.STRING,
            capacity=8,
            initial=initial,
        )


@pytest.mark.parametrize(
    ("data_type", "initial", "message"),
    [
        (ir.DataType.REAL, "1.0", "int or float"),
        (ir.DataType.INTEGER, 1.0, "must be an int"),
        (ir.DataType.INTEGER, True, "must be an int"),
        (ir.DataType.BOOLEAN, 1, "must be a bool"),
    ],
)
def test_initial_value_must_match_the_data_type(
    data_type: ir.DataType, initial: object, message: str
) -> None:
    with pytest.raises(ir.ProjectionError, match=message):
        _signal("bad", data_type=data_type, initial=initial)


def test_string_capacity_is_a_utf8_byte_budget() -> None:
    exact = _signal(
        "label",
        data_type=ir.DataType.STRING,
        capacity=2,
        initial="å",
    )
    assert exact.wire_capacity == 2
    assert exact.initial_bytes == "å".encode("utf-8")
    assert ir.encode_string("å", 2) == b"\xc3\xa5"

    with pytest.raises(ir.ProjectionError, match="exceeding capacity 2"):
        _signal(
            "label",
            data_type=ir.DataType.STRING,
            capacity=2,
            initial="åå",
        )


def test_strings_may_not_contain_nul() -> None:
    with pytest.raises(ir.ProjectionError, match="must not contain NUL"):
        _signal("label", data_type=ir.DataType.STRING, capacity=8, initial="a\0b")
    with pytest.raises(ir.ProjectionError, match="must not contain NUL"):
        ir.encode_string("a\0b", 8)


def test_units_distinguish_unspecified_from_dimensionless(tmp_path) -> None:
    model = _model(
        _signal(
            "unspecified",
            1,
            data_type=ir.DataType.STRING,
            capacity=4,
            unit=None,
        ),
        _signal(
            "dimensionless",
            2,
            data_type=ir.DataType.STRING,
            capacity=4,
            unit="",
        ),
    )

    payload = ir.model_to_dict(model)
    assert [item["unit"] for item in payload["signals"]] == [None, ""]

    encoded = json.dumps(payload, sort_keys=True)
    restored = ir.model_from_dict(json.loads(encoded))
    assert [item["unit"] for item in ir.model_to_dict(restored)["signals"]] == [None, ""]
    assert json.dumps(ir.model_to_dict(restored), sort_keys=True) == encoded

    ir.write_model_json(model, tmp_path / "model.json")
    text = (tmp_path / "model.json").read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_non_string_units_are_rejected() -> None:
    with pytest.raises(ir.ProjectionError, match="unit must be a string or None"):
        _signal("bad", unit=5)  # type: ignore[arg-type]
