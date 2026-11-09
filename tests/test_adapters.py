from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyfmi_distributed.adapters import (
    ADAPTERS,
    adapter_manifest,
    get_adapter,
    vcpkg_features,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VCPKG_MANIFEST = REPO_ROOT / "vcpkg.json"

pytestmark = pytest.mark.unit

# The catalogue can name only the primary port. DCPLib and ED247_LIBRARY are
# fetched from source, so their vcpkg features also list the support ports.
SUPPORT_PORTS = {
    "hla": set(),
    "dis": set(),
    "dcp": {"asio", "xerces-c", "libzip"},
    "ros2": set(),
    "ed247": {"libxml2"},
}


def test_dcp_is_asam_xdcp_not_dds():
    dcp = get_adapter("dcp")

    assert dcp.display_name == "ASAM X-DCP"
    assert "Distributed Co-Simulation Protocol" in dcp.summary
    assert "DDS" not in dcp.summary
    assert "DDS" not in " ".join(dcp.requires)
    assert dcp.requires == ("DCPLib",)
    assert dcp.dependency is not None
    assert dcp.dependency.upstream == "https://github.com/modelica/DCPLib"
    assert dcp.dependency.pin == "v0.2"
    assert dcp.dependency.license == "BSD-3-Clause"


@pytest.mark.parametrize("name", sorted(name for name in ADAPTERS if name != "loopback"))
def test_non_loopback_dependency_records_acquisition_metadata(name):
    dependency = get_adapter(name).dependency

    assert dependency is not None
    assert dependency.acquisition in {"vcpkg", "fetchcontent", "system"}
    assert dependency.upstream
    assert dependency.pin
    assert dependency.license
    assert dependency.cmake_package
    assert dependency.cmake_targets
    assert dependency.submodule_path or dependency.acquisition == "system"


@pytest.mark.contract
def test_vcpkg_features_match_manifest():
    manifest = json.loads(VCPKG_MANIFEST.read_text(encoding="utf-8"))
    # vcpkg_features() keys every adapter; loopback is built in and has no
    # manifest feature, so it is excluded from the contract.
    features = {name: ports for name, ports in vcpkg_features().items() if name != "loopback"}

    assert set(features) == set(manifest["features"])
    for name, ports in features.items():
        declared = set(manifest["features"][name].get("dependencies", []))
        assert declared == set(ports) | SUPPORT_PORTS[name]


def test_adapter_manifest_is_json_serializable_with_one_row_per_adapter():
    manifest = adapter_manifest()
    encoded = json.dumps(manifest)

    assert json.loads(encoded) == manifest
    assert len(manifest) == len(ADAPTERS)
    assert {row["name"] for row in manifest} == set(ADAPTERS)


def test_ros2_is_system_install_only():
    dependency = get_adapter("ros2").dependency

    assert dependency is not None
    assert dependency.acquisition == "system"
    assert dependency.vcpkg_port is None
    assert dependency.cmake_package == "rclcpp"
    assert dependency.submodule_path is None
