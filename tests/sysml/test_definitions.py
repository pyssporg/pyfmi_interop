"""The bundled ``PyfmiInterop`` SysML library and its packaging."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pyfmi_interop import interop_definitions

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.sysml


@pytest.mark.unit
def test_interop_definitions_is_a_bundled_file():
    path = interop_definitions()

    assert path.name == "interop.sysml"
    assert path.parent.name == "definitions"
    assert path.is_file()


@pytest.mark.unit
def test_interop_definitions_declares_the_shared_vocabulary():
    pycps = pytest.importorskip("pycps_sysml2")
    architecture = pycps.load(interop_definitions())

    assert architecture.package_name == "PyfmiInterop"

    metadata = next(
        definition
        for definition in architecture.attribute_definitions.values()
        if definition.name == "InteropMetadata"
    )
    assert "FmuMetadata" not in metadata.specializes
    assert set(metadata.attributes) == {"source", "serialization", "version"}

    deployment = next(
        definition
        for definition in architecture.port_definitions.values()
        if definition.name == "InteropDeployment"
    )
    assert "ParameterInterface" in deployment.specializes
    assert set(deployment.attributes) == {
        "transport",
        "bind_address",
        "peer_address",
    }

    model = next(
        definition
        for definition in architecture.part_definitions.values()
        if definition.name == "FmuInterop"
    )
    assert "FmuModel" in model.specializes
    assert "interop_meta" in model.attributes
    assert "parameters" in model.ports
    # fmu_meta stays inherited from FmuModel, not redeclared locally.
    assert "fmu_meta" not in model.attributes


@pytest.mark.static
def test_sysml_library_is_declared_as_package_data():
    manifest = (_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include src/pyfmi_interop/definitions *.sysml" in manifest

    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data = pyproject["tool"]["setuptools"]["package-data"]["pyfmi_interop"]
    assert "definitions/*.sysml" in data
