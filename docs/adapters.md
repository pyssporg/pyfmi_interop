# Adapters

A transport adapter maps model signals onto a channel of an external protocol.
Every adapter implements the same `Transport` interface and exchanges
preallocated `Sample` frames. Protocol serialization is never reimplemented in
this repository: each adapter binds the prebuilt upstream library through its
public API, and the mapping code lives in `runtime/src/adapters/`.

DCP is the ASAM **Distributed Co-Simulation Protocol** (X-DCP), implemented by
DCPLib. It is not DDS; DDS is a separate transport and has no adapter here.

## Dependency table

| Adapter | Standard | CMake gate | Upstream library | Pin | License | Acquisition | CMake targets | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| loopback | in-process frames | none, always built | — | — | — | built in | — | stable, implemented |
| HLA | IEEE 1516 HLA | `PYFMI_DIST_ENABLE_HLA` | [OpenRTI](https://github.com/onox/OpenRTI) | `fb454e6` (0.10.0) | LGPL-2.1 / LGPL-3.0 / MPL-2.0 | submodule or FetchContent (no vcpkg port) | `rti1516e` (`pkg-config rti1516e` when installed) | skeleton, experimental |
| DIS | IEEE 1278 DIS | `PYFMI_DIST_ENABLE_DIS` | [open-dis-cpp](https://github.com/open-dis/open-dis-cpp) | `v1.2.0` (vcpkg snapshot has 1.1.0) | BSD-2-Clause | vcpkg port `open-dis-cpp` (submodule/FetchContent fallback) | `OpenDIS::OpenDIS7` | skeleton, experimental |
| DCP | ASAM X-DCP, Distributed Co-Simulation Protocol | `PYFMI_DIST_ENABLE_DCP` | [DCPLib](https://github.com/modelica/DCPLib) | `v0.2` | BSD-3-Clause | submodule or FetchContent (no vcpkg port; asio, xerces-c, libzip from vcpkg) | `DCPLib::Core`, `DCPLib::Slave`, `DCPLib::Master`, `DCPLib::Ethernet` | skeleton, experimental |
| ROS 2 | ROS 2 Jazzy | `PYFMI_DIST_ENABLE_ROS2` | [`rclcpp`](https://github.com/ros2/rclcpp) | Jazzy (`release-jazzy-20260618`) | Apache-2.0 | system only: `source /opt/ros/jazzy/setup.bash`; never vendored | `rclcpp::rclcpp` | skeleton, experimental |
| ED-247 | ED-247 (ARINC 664) | `PYFMI_DIST_ENABLE_ED247` | [Airbus ED247_LIBRARY](https://github.com/airbus/ED247_LIBRARY) | `VA2.3.0` | MIT | submodule or FetchContent (no vcpkg port, no installed package config; libxml2 from vcpkg) | `Ed247::static` | skeleton, experimental |

The catalogue is `src/pyfmi_distributed/adapters.py`; the CLI, the CMake build,
`vcpkg.json`, and this table read the same `AdapterDependency` metadata.

## Status

Only loopback is implemented and always compiled. The other five adapters ship
as compile-gated skeletons that use the prebuilt library APIs:

- the option defaults to OFF, so no external library is a hard build dependency;
- a skeleton still links and reports `available() == false`;
- `initialize()` on an unbuilt adapter fails with a message naming the missing
  library;
- enabling an option does not create a working binding where the protocol
  mapping has not been written.

Do not describe a gated adapter as implemented until its binding has tests
against a real or simulated endpoint and this table says so.

## Acquisition order

`cmake/adapters.cmake` resolves each enabled adapter in this order:

1. **Installed package.** `find_package()` discovers a vcpkg or system
   installation (for ROS 2, the system Jazzy installation).
2. **Submodule checkout.** `third_party/<lib>` is used when it exists and
   `PYFMI_DIST_USE_SUBMODULES=ON` (default ON).
3. **FetchContent.** The pinned upstream revision is downloaded when
   `-DPYFMI_DIST_ALLOW_FETCH=ON` (default OFF).
4. **Hard error.** Configuration fails with the upstream URL, pin, and the
   acquisition instructions. It never falls back to a stub or another
   transport.

The repository never reimplements protocol serialization; it only maps model
signals onto the library API in `runtime/src/adapters/`.

### vcpkg

```bash
vcpkg install --feature-flags=manifests \
  --x-manifest-root=. --x-install-root=vcpkg_installed
```

Or use manifest mode through the CMake toolchain and select the features:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" \
  -DVCPKG_MANIFEST_MODE=ON \
  -DVCPKG_MANIFEST_FEATURES="dis;dcp" \
  -DPYFMI_DIST_ENABLE_DIS=ON -DPYFMI_DIST_ENABLE_DCP=ON
cmake --build build
```

Add `--x-feature=<name>` to the `vcpkg install` command when installing a
feature outside CMake manifest mode.

### Submodule

```bash
git submodule add <url> third_party/<name>
git -C third_party/<name> checkout <pin>
```

For example:

```bash
git submodule add https://github.com/modelica/DCPLib third_party/DCPLib
git -C third_party/DCPLib checkout v0.2
```

Submodule checkouts are preferred over downloads by default. ROS 2 is the
exception: `rclcpp` is an ament distribution and must come from
`/opt/ros/jazzy`, never from a submodule or FetchContent.

### FetchContent

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DPYFMI_DIST_ENABLE_DCP=ON \
  -DPYFMI_DIST_ALLOW_FETCH=ON
cmake --build build
```

## Enable an adapter

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DPYFMI_DIST_ENABLE_HLA=ON \
  -DPYFMI_DIST_USE_SUBMODULES=ON
cmake --build build
```

If the library is absent and neither a submodule nor FetchContent provides it,
configuration fails and names the requirement. Keep the option OFF rather than
inventing a replacement.

## Add an adapter

Adding a protocol adapter is deliberately mechanical:

1. **One descriptor** in `src/pyfmi_distributed/adapters.py`: name, display
   name, kind, CMake option, C++ class, summary, external requirement, and
   `AdapterDependency` (acquisition, upstream, pin, license, targets, submodule
   path).
2. **One implementation** at `runtime/src/adapters/<name>.cpp`, implementing
   `Transport::initialize`, `finalize`, `available`, `send`, and `receive`
   against the upstream library API.
3. **One header** at
   `runtime/include/pyfmi_distributed/runtime/adapters/<name>.hpp`, exposing
   the adapter class.
4. **Register** the source in `runtime/CMakeLists.txt`, add the option to
   `PYFMI_DIST_RUNTIME_OPTIONS`, add the acquisition function to
   `cmake/adapters.cmake`, and add the vcpkg feature to `vcpkg.json`.
5. **Document** the row here and add the library gate to CI as an optional job,
   not a required one.

Nothing else may grow a protocol-specific branch. The generated model talks to
the adapter through the `Transport` interface and the binding hooks, so codegen
does not change when an adapter is added.

## Failure behaviour

- Unknown adapter name: the registry returns `nullptr` and lists the known
  transports.
- Option OFF: the stub reports unavailable; initialization fails.
- Option ON, library missing: configuration fails with the upstream URL, pin,
  and acquisition instructions.
- Configuration rejected: initialization fails with the adapter's reason.
- Send or receive failure: the scheduler surfaces the error; it does not switch
  transports.

No adapter silently substitutes for another. A realtime run either uses the
configured transport or reports that it cannot.

## Pinned checkouts and upstream build notes

The adapter libraries are pinned as git submodules:

| Path | Upstream | Pin |
| --- | --- | --- |
| `third_party/OpenRTI` | `https://github.com/onox/OpenRTI.git` | `fb454e6` (0.10.0 version bump) |
| `third_party/DCPLib` | `https://github.com/modelica/DCPLib.git` | `v0.2` |
| `third_party/ED247_LIBRARY` | `https://github.com/airbus/ED247_LIBRARY.git` | `VA2.3.0` |

DIS is taken from the vcpkg port `open-dis-cpp`; ROS 2 from the system Jazzy
installation. Neither is a submodule.

Two pinned upstream trees need a build-only workaround. Neither workaround
modifies the submodule working tree:

- **OpenRTI** assumes it is the top-level CMake project (it uses
  `CMAKE_SOURCE_DIR`) and unconditionally builds its tests. The adapter module
  prepares a build-tree copy with the source/binary root variables rebound and
  the test subtree removed, then embeds that copy.
- **ED247_LIBRARY** `VA2.3.0` uses `std::numeric_limits` without including
  `<limits>`, which newer libstdc++ no longer pulls in transitively. The module
  force-includes `<limits>` for the library's own objects.

Bump a pin by changing the descriptor in `src/pyfmi_distributed/adapters.py`,
checking out the new revision in the submodule, and re-running the adapter build
with `-DPYFMI_DIST_ENABLE_<NAME>=ON`.
