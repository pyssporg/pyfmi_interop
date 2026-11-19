"""Adapter catalogue: the single source of truth for transport names.

The Python generator, the CMake build, the vcpkg manifest, and the
documentation all read this table.  Adding an adapter means adding one
:class:`AdapterDescriptor` here and one source unit under
``runtime/src/adapters/``; nothing else may grow a protocol-specific branch.

Protocol libraries are never reimplemented in this repository.  Each
descriptor names the upstream project, the pinned revision, the license, and
how the build obtains it: from vcpkg where a port exists, otherwise from a
submodule checkout or FetchContent.  ROS 2 is consumed from a system install
because it is an ament distribution, not a standalone CMake package.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AdapterDependency",
    "AdapterDescriptor",
    "ADAPTERS",
    "LOOPBACK",
    "adapter_cmake_flags",
    "adapter_manifest",
    "available_adapters",
    "get_adapter",
    "require_adapter",
    "vcpkg_features",
]


@dataclass(frozen=True)
class AdapterDependency:
    """How the build obtains one upstream protocol library.

    ``acquisition`` is ``"vcpkg"`` (port exists, preferred), ``"fetchcontent"``
    (pinned source download or submodule), or ``"system"`` (must be installed
    by the operator, e.g. a ROS 2 distribution).
    """

    acquisition: str
    upstream: str
    pin: str
    license: str
    vcpkg_port: str | None = None
    cmake_package: str | None = None
    cmake_targets: tuple[str, ...] = ()
    submodule_path: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.acquisition not in {"vcpkg", "fetchcontent", "system"}:
            raise ValueError(f"unknown acquisition mode: {self.acquisition}")


@dataclass(frozen=True)
class AdapterDescriptor:
    """Static description of one transport backend.

    ``cmake_option`` names the compile gate.  With the option OFF the runtime
    keeps a stub that reports ``available() == false`` and refuses to
    initialize, so a generated model always builds on a machine without the
    protocol SDK.  With the option ON the real library is required and the
    build fails loudly if it cannot be resolved: a half-adapter is worse than
    no adapter.
    """

    name: str
    display_name: str
    kind: str
    cmake_option: str
    cpp_class: str
    summary: str
    requires: tuple[str, ...] = ()
    dependency: AdapterDependency | None = None
    experimental: bool = False


LOOPBACK = AdapterDescriptor(
    name="loopback",
    display_name="In-process loopback",
    kind="local",
    cmake_option="",  # always built
    cpp_class="LoopbackTransport",
    summary=(
        "Single-process transport used for tests and for running a generated "
        "model without a network. Signals are stored in preallocated frames."
    ),
)

ADAPTERS: dict[str, AdapterDescriptor] = {
    "loopback": LOOPBACK,
    "hla": AdapterDescriptor(
        name="hla",
        display_name="IEEE 1516 HLA",
        kind="federation",
        cmake_option="PYFMI_INTEROP_ENABLE_HLA",
        cpp_class="HlaTransport",
        summary=(
            "High Level Architecture federation adapter. Maps signals onto "
            "interactions and object attributes through an RTI ambassador."
        ),
        requires=("OpenRTI or another IEEE 1516 RTI",),
        dependency=AdapterDependency(
            acquisition="fetchcontent",
            upstream="https://github.com/onox/OpenRTI",
            # 0.10.0 release; no matching git tag, so pin the version-bump
            # commit. Switch to the SourceForge tarball if git access is
            # unavailable.
            pin="fb454e6",
            license="LGPL-2.1 / LGPL-3.0 / MPL-2.0",
            cmake_package="OpenRTI",
            cmake_targets=("rti1516e",),
            submodule_path="third_party/OpenRTI",
            note=(
                "OpenRTI installs pkg-config files, not a CMake package config. "
                "Disable OPENRTI_ENABLE_PYTHON_BINDINGS."
            ),
        ),
        experimental=True,
    ),
    "dis": AdapterDescriptor(
        name="dis",
        display_name="IEEE 1278 DIS",
        kind="federation",
        cmake_option="PYFMI_INTEROP_ENABLE_DIS",
        cpp_class="DisTransport",
        summary=(
            "Distributed Interactive Simulation adapter. Maps signals onto "
            "entity state and attribute PDUs over UDP multicast."
        ),
        requires=("open-dis-cpp",),
        dependency=AdapterDependency(
            acquisition="vcpkg",
            upstream="https://github.com/open-dis/open-dis-cpp",
            pin="v1.2.0",
            license="BSD-2-Clause",
            vcpkg_port="open-dis-cpp",
            cmake_package="OpenDIS",
            cmake_targets=("OpenDIS::OpenDIS7",),
            submodule_path="third_party/open-dis-cpp",
            note=(
                "vcpkg carries 1.1.0; FetchContent pins v1.2.0. Link "
                "OpenDIS::OpenDIS7 (or the un-namespaced OpenDIS7 target in a "
                "FetchContent build)."
            ),
        ),
        experimental=True,
    ),
    "dcp": AdapterDescriptor(
        name="dcp",
        display_name="ASAM X-DCP",
        kind="protocol",
        cmake_option="PYFMI_INTEROP_ENABLE_DCP",
        cpp_class="DcpTransport",
        summary=(
            "ASAM Distributed Co-Simulation Protocol adapter. Maps signals "
            "onto X-DCP signals and drives a DCP slave or master connection."
        ),
        requires=("DCPLib",),
        dependency=AdapterDependency(
            acquisition="fetchcontent",
            upstream="https://github.com/modelica/DCPLib",
            # Only upstream tag; HEAD keeps receiving fixes. Prefer the tag for
            # reproducibility and revisit when a newer tag appears.
            pin="v0.2",
            license="BSD-3-Clause",
            cmake_package="DCPLib",
            cmake_targets=(
                "DCPLib::Core",
                "DCPLib::Slave",
                "DCPLib::Master",
                "DCPLib::Ethernet",
            ),
            submodule_path="third_party/DCPLib",
            note=(
                "Needs asio, xerces-c and libzip. The top-level project always "
                "builds its mytest target; build only the library targets."
            ),
        ),
        experimental=True,
    ),
    "ros2": AdapterDescriptor(
        name="ros2",
        display_name="ROS 2",
        kind="middleware",
        cmake_option="PYFMI_INTEROP_ENABLE_ROS2",
        cpp_class="Ros2Transport",
        summary=(
            "ROS 2 adapter. Maps signals onto topics and performs the callback "
            "exchange on an executor thread outside the step deadline."
        ),
        requires=("ROS 2 Jazzy (rclcpp)",),
        dependency=AdapterDependency(
            acquisition="system",
            upstream="https://github.com/ros2/rclcpp",
            pin="Jazzy (release-jazzy-20260618)",
            license="Apache-2.0",
            cmake_package="rclcpp",
            cmake_targets=("rclcpp::rclcpp",),
            note=(
                "Source /opt/ros/jazzy/setup.bash before configuring. rclcpp is "
                "an ament distribution and must not be vendored as a submodule."
            ),
        ),
        experimental=True,
    ),
    "ed247": AdapterDescriptor(
        name="ed247",
        display_name="ED-247 (ARINC 664)",
        kind="avionics",
        cmake_option="PYFMI_INTEROP_ENABLE_ED247",
        cpp_class="Ed247Transport",
        summary=(
            "ED-247 avionics adapter. Maps signals onto configured streams and "
            "performs deadline-checked reads and writes."
        ),
        requires=("Airbus ED247_LIBRARY",),
        dependency=AdapterDependency(
            acquisition="fetchcontent",
            upstream="https://github.com/airbus/ED247_LIBRARY",
            pin="VA2.3.0",
            license="MIT",
            vcpkg_port=None,
            cmake_package="Ed247",
            cmake_targets=("Ed247::static",),
            submodule_path="third_party/ED247_LIBRARY",
            note=(
                "Requires LibXml2 >= 2.9.1. No installed package config; link "
                "the in-tree ed247_static target."
            ),
        ),
        experimental=True,
    ),
}

_EXTERNAL = tuple(name for name in ADAPTERS if name != "loopback")


def get_adapter(name: str) -> AdapterDescriptor:
    try:
        return ADAPTERS[name]
    except KeyError as error:
        known = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"unknown adapter {name!r}; known adapters: {known}") from error


def require_adapter(name: str) -> AdapterDescriptor:
    """Like :func:`get_adapter` but also rejects experimental-only adapters.

    Callers that need a *buildable* adapter use this; the CLI reports the
    missing SDK instead of generating a model that cannot be compiled.
    """

    descriptor = get_adapter(name)
    if descriptor.experimental:
        requirement = ", ".join(descriptor.requires) or "an external SDK"
        raise ValueError(
            f"adapter {name!r} is experimental and requires {requirement}; "
            "enable it explicitly with the matching CMake option"
        )
    return descriptor


def available_adapters() -> tuple[AdapterDescriptor, ...]:
    return tuple(ADAPTERS[name] for name in sorted(ADAPTERS))


def adapter_cmake_flags(names: object) -> list[str]:
    """Return CMake ``-D`` arguments for the requested adapter names."""

    requested = {str(name) for name in names}  # type: ignore[arg-type]
    flags: list[str] = []
    for name in sorted(requested):
        descriptor = get_adapter(name)
        if not descriptor.cmake_option:
            continue
        flags.append(f"-D{descriptor.cmake_option}=ON")
    return flags


def vcpkg_features() -> dict[str, tuple[str, ...]]:
    """Return vcpkg feature -> port dependencies derived from the catalogue."""

    features: dict[str, tuple[str, ...]] = {}
    for name in sorted(ADAPTERS):
        descriptor = ADAPTERS[name]
        if descriptor.dependency is None:
            # Built-in adapters (loopback) have no external dependency and no
            # vcpkg feature.
            continue
        dependency = descriptor.dependency
        features[name] = () if dependency.vcpkg_port is None else (dependency.vcpkg_port,)
    return features


def adapter_manifest() -> list[dict[str, object]]:
    """Machine-readable adapter table used by the docs and the CLI."""

    manifest: list[dict[str, object]] = []
    for name in sorted(ADAPTERS):
        descriptor = ADAPTERS[name]
        dependency = descriptor.dependency
        manifest.append(
            {
                "name": descriptor.name,
                "display_name": descriptor.display_name,
                "kind": descriptor.kind,
                "cmake_option": descriptor.cmake_option,
                "experimental": descriptor.experimental,
                "requires": list(descriptor.requires),
                "acquisition": None if dependency is None else dependency.acquisition,
                "upstream": None if dependency is None else dependency.upstream,
                "pin": None if dependency is None else dependency.pin,
                "license": None if dependency is None else dependency.license,
                "vcpkg_port": None if dependency is None else dependency.vcpkg_port,
            }
        )
    return manifest
