from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pyfmi_interop.ir import (
    DataType,
    Direction,
    ModelDefinition,
    ProjectionError,
    RateGroup,
    Signal,
    deterministic_guid,
)
from pyfmi_interop.schema import (
    SCHEMA_FORMAT_VERSION,
    build_schema,
    proto_filename,
    render_proto,
    render_wire_json,
    schema_entries,
    write_schema,
)
from pyfmi_interop.wire import model_id

_GOLDEN = Path(__file__).resolve().parent / "golden"


def make_model() -> ModelDefinition:
    signals = (
        Signal("speed", 1, DataType.REAL, Direction.OUTPUT, unit="m/s", initial=1.5),
        Signal("setpoint", 5, DataType.REAL, Direction.INPUT, rate_hz=50.0),
        Signal("label", 2, DataType.STRING, Direction.OUTPUT, capacity=16, initial="hi"),
        Signal("enable", 3, DataType.BOOLEAN, Direction.PARAMETER, initial=True),
        Signal("mode", 4, DataType.INTEGER, Direction.PARAMETER, initial=2),
    )
    return ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=signals,
        rate_groups=(RateGroup("fast", 0.02, 0.01, ("setpoint",)),),
    )


def test_proto_projects_every_signal_with_its_ir_id():
    model = make_model()
    text = render_proto(model)
    fields = {
        int(match.group(2)): match.group(1)
        for match in re.finditer(r"^  Value (\w+) = (\d+);$", text, re.MULTILINE)
    }

    assert fields == {
        signal.value_reference: signal.name
        for signal in sorted(model.signals, key=lambda item: item.value_reference)
    }
    assert 'syntax = "proto3";' in text
    assert "package pyfmi_interop.wire;" in text
    assert "message demo_model {" in text
    assert "  reserved 19000 to 19999;" in text


def test_proto_golden_snippet_carries_type_direction_rate_unit_capacity():
    text = render_proto(make_model())

    assert (
        "  // name=speed type=real direction=output rate=base unit=m/s capacity=0\n"
        "  Value speed = 1;\n"
    ) in text
    assert (
        "  // name=label type=string direction=output rate=base "
        "unit=unspecified capacity=16\n"
        "  Value label = 2;\n"
    ) in text
    assert (
        "  // name=setpoint type=real direction=input rate=50.0 Hz "
        "unit=unspecified capacity=0\n"
        "  Value setpoint = 5;\n"
    ) in text


def test_part_definition_name_is_the_message_name():
    model = ModelDefinition(
        name="Demo",
        guid=deterministic_guid("Demo"),
        step_size_s=0.01,
        signals=(Signal("out.value", 1, DataType.REAL, Direction.OUTPUT),),
        interface="Demo.Plant",
    )

    text = render_proto(model)
    payload = json.loads(render_wire_json(model))

    assert "message Demo_Plant {" in text
    assert "DemoPayload" not in text
    assert payload["payload_message"] == "Demo_Plant"
    assert payload["interface"] == "Demo.Plant"


def test_identifier_collision_is_an_error_not_a_rename():
    model = ModelDefinition(
        name="Demo",
        guid=deterministic_guid("Demo"),
        step_size_s=0.01,
        signals=(
            Signal("a_b.c", 1, DataType.REAL, Direction.OUTPUT),
            Signal("a.b_c", 2, DataType.REAL, Direction.OUTPUT),
        ),
    )

    with pytest.raises(ProjectionError, match="collision"):
        render_proto(model)
    with pytest.raises(ProjectionError, match="collision"):
        render_wire_json(model)


def test_array_elements_are_one_scalar_field_each():
    model = ModelDefinition(
        name="Demo",
        guid=deterministic_guid("Demo"),
        step_size_s=0.01,
        signals=(
            Signal("out.arr[0]", 1, DataType.REAL, Direction.OUTPUT),
            Signal("out.arr[1]", 2, DataType.REAL, Direction.OUTPUT),
        ),
        interface="Plant",
    )

    text = render_proto(model)
    payload = json.loads(render_wire_json(model))

    assert "Value out_arr_0 = 1;" in text
    assert "Value out_arr_1 = 2;" in text
    assert "repeated" not in text
    assert [item["field"] for item in payload["signals"]] == [
        "out_arr_0",
        "out_arr_1",
    ]


def test_wire_direction_inverts_fmi_causality():
    payload = json.loads(render_wire_json(make_model()))
    directions = {item["name"]: item["wire"] for item in payload["signals"]}

    assert directions == {
        "speed": "in",  # FMI output
        "setpoint": "out",  # FMI input
        "label": "in",  # FMI output
        "enable": "none",  # parameter
        "mode": "none",  # parameter
    }


def test_wire_json_projects_every_signal_with_ir_metadata():
    model = make_model()
    payload = json.loads(render_wire_json(model))

    assert payload["format_version"] == SCHEMA_FORMAT_VERSION
    assert payload["format"] == "protobuf"
    assert payload["format_id"] == 1
    assert payload["model"] == "demo_model"
    assert payload["interface"] == "demo_model"
    assert payload["role"] == "adapter"
    assert payload["guid"] == deterministic_guid("demo_model")
    assert payload["model_id"] == model_id(model).hex()
    assert payload["step_size_s"] == 0.01
    assert payload["payload_message"] == "demo_model"
    assert payload["rate_groups"] == [
        {
            "deadline_s": 0.01,
            "name": "fast",
            "period_s": 0.02,
            "signals": ["setpoint"],
        }
    ]
    assert payload["signals"] == [
        {
            "capacity": 0,
            "data_type": "real",
            "direction": "output",
            "field": "speed",
            "id": 1,
            "name": "speed",
            "rate_hz": None,
            "unit": "m/s",
            "wire": "in",
        },
        {
            "capacity": 16,
            "data_type": "string",
            "direction": "output",
            "field": "label",
            "id": 2,
            "name": "label",
            "rate_hz": None,
            "unit": None,
            "wire": "in",
        },
        {
            "capacity": 0,
            "data_type": "boolean",
            "direction": "parameter",
            "field": "enable",
            "id": 3,
            "name": "enable",
            "rate_hz": None,
            "unit": None,
            "wire": "none",
        },
        {
            "capacity": 0,
            "data_type": "integer",
            "direction": "parameter",
            "field": "mode",
            "id": 4,
            "name": "mode",
            "rate_hz": None,
            "unit": None,
            "wire": "none",
        },
        {
            "capacity": 0,
            "data_type": "real",
            "direction": "input",
            "field": "setpoint",
            "id": 5,
            "name": "setpoint",
            "rate_hz": 50.0,
            "unit": None,
            "wire": "out",
        },
    ]


def test_backends_change_the_descriptor_format_only():
    packed = json.loads(render_wire_json(make_model(), serialization="packed"))
    opaque = json.loads(render_wire_json(make_model(), serialization="opaque"))

    assert (packed["format"], packed["format_id"]) == ("packed", 2)
    assert (opaque["format"], opaque["format_id"]) == ("opaque", 0)


def test_wire_json_golden_snippet_is_sorted_and_has_no_paths_or_timestamps():
    model = make_model()
    text = render_wire_json(model)

    assert f'"model_id": "{model_id(model).hex()}",' in text
    assert text.startswith('{\n  "format": "protobuf",')
    keys = list(json.loads(text))
    assert keys == sorted(keys)
    assert "/" not in text.replace("m/s", "").replace("pyfmi_interop.wire", "")
    assert "time" not in json.loads(text)


def test_protobuf_artifacts_match_the_checked_in_golden():
    model = make_model()
    bundle = build_schema(model)

    assert bundle.proto_name == "demo_model.proto"
    assert bundle.proto == (_GOLDEN / "demo_model.proto").read_bytes()
    assert bundle.wire_json == (_GOLDEN / "demo_model.wire.json").read_bytes()


def test_artifacts_are_byte_identical_when_emitted_twice(tmp_path):
    model = make_model()

    first = build_schema(model)
    second = build_schema(model)
    assert first == second
    assert first.proto_name == proto_filename(model) == "demo_model.proto"
    assert first.wire_json_name == "wire.json"

    write_schema(model, tmp_path / "a")
    write_schema(model, tmp_path / "b")
    for name in ("demo_model.proto", "wire.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_schema_entries_use_the_requested_directory():
    entries = schema_entries(make_model(), prefix="binaries/linux64")

    assert set(entries) == {
        "binaries/linux64/demo_model.proto",
        "binaries/linux64/wire.json",
    }


def test_packed_and_opaque_bundles_have_no_proto():
    for name in ("packed", "opaque"):
        entries = schema_entries(
            make_model(), prefix="binaries/linux64", serialization=name
        )
        assert set(entries) == {"binaries/linux64/wire.json"}


def test_non_projectable_signal_raises_instead_of_being_dropped():
    model = ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=(Signal("bad\x00name", 1, DataType.REAL, Direction.OUTPUT),),
    )

    with pytest.raises(ProjectionError) as proto_error:
        render_proto(model)
    assert proto_error.value.signal_name == "bad\x00name"

    with pytest.raises(ProjectionError) as json_error:
        render_wire_json(model)
    assert json_error.value.signal_name == "bad\x00name"


def test_duplicate_value_reference_raises_instead_of_overwriting():
    model = ModelDefinition(
        name="demo_model",
        guid=deterministic_guid("demo_model"),
        step_size_s=0.01,
        signals=(
            Signal("speed", 1, DataType.REAL, Direction.OUTPUT),
            Signal("altitude", 1, DataType.REAL, Direction.OUTPUT),
        ),
    )

    with pytest.raises(ProjectionError, match="duplicate value reference 1"):
        render_proto(model)


@pytest.mark.skipif(
    importlib.util.find_spec("grpc_tools") is None,
    reason="grpc_tools is not installed",
)
def test_proto_compiles_with_protoc(tmp_path):
    write_schema(make_model(), tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={tmp_path}",
            f"--python_out={tmp_path}",
            str(tmp_path / "demo_model.proto"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "demo_model_pb2.py").is_file()
