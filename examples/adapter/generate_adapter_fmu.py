"""Generate an adapter FMU from a SysML v2 part definition, without the CLI.

The pipeline is the public Python API, in four calls:

1. :func:`pyfmi_interop.sysml.load_model` reduces the SysML interface to the IR.
2. :func:`pyfmi_interop.generate_model` emits the C++ adapter source tree.
3. :func:`pyfmi_interop.build_model` configures and builds it with CMake.
4. :func:`pyfmi_interop.package_fmu` writes the deterministic FMI 2.0 archive.

Everything is written under ``--out`` (default ``build/examples/adapter/``),
which is gitignored.  The script prints the derived role, the payload message
and format, the field table, and example transport URIs so a peer can be
pointed at the same wire schema.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyfmi_interop import (
    build_model,
    generate_model,
    model_from_dict,
    package_fmu,
)
from pyfmi_interop.roles import ROLES
from pyfmi_interop.sysml import load_model

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
DEFAULT_SYSML = EXAMPLE_DIR / "actuator_link.sysml"
DEFAULT_NAME = "ActuatorLinkAdapter"
DEFAULT_OUT_ROOT = REPO_ROOT / "build" / "examples" / "adapter"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate, build and package the ActuatorLink adapter FMU.",
    )
    parser.add_argument("--sysml", type=Path, default=DEFAULT_SYSML)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output root (default: {DEFAULT_OUT_ROOT}/<serialization>).",
    )
    parser.add_argument(
        "--serialization",
        choices=("protobuf", "packed"),
        default="protobuf",
        help="Payload serialization backend (default: protobuf).",
    )
    parser.add_argument("--name", default=DEFAULT_NAME, help="FMI model name.")
    parser.add_argument(
        "--step-size",
        type=float,
        default=None,
        dest="step_size",
        help="Base step size in seconds (default: from SysML, else 0.001).",
    )
    parser.add_argument(
        "--role",
        choices=ROLES,
        default=None,
        help="Narrow the role derived from FMI causality.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    out_root = args.out or DEFAULT_OUT_ROOT / args.serialization
    model_dir = out_root / "model"
    build_dir = out_root / "build"

    # 1. SysML interface -> IR.  The part definition's ports become signals.
    model = load_model(
        args.sysml,
        name=args.name,
        step_size_s=args.step_size,
        realtime=True,
    )

    # 2. IR -> C++ adapter sources, wire schema and model.json.
    generate_model(
        model,
        model_dir,
        serialization=args.serialization,
        role=args.role,
    )

    # 3. C++ sources -> shared library (links runtime and transport archives).
    library = build_model(model_dir, build_dir=build_dir)

    # 4. Generated model.json carries the resolved role and serialization.
    effective = model_from_dict(
        json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
    )
    fmu_path = out_root / f"{effective.name}.fmu"
    package_fmu(model_dir, library, fmu_path, model=effective)

    _print_summary(model_dir, fmu_path)
    return 0


def _print_summary(model_dir: Path, fmu_path: Path) -> None:
    wire = json.loads((model_dir / "wire.json").read_text(encoding="utf-8"))
    print(f"role: {wire['role']}")
    print(
        f"payload: {wire['payload_message']} "
        f"(format={wire['format']}, format_id={wire['format_id']})"
    )
    print(f"step_size_s: {wire['step_size_s']}")
    print(f"{'field':<24} {'vr':>3} {'causality':<9} wire")
    for signal in wire["signals"]:
        print(
            f"{signal['field']:<24} {signal['id']:>3} "
            f"{signal['direction']:<9} {signal['wire']}"
        )
    print("transport URIs:")
    print("  loopback")
    print("  udp://127.0.0.1:5000?peer=127.0.0.1:5001")
    print("  tcp://127.0.0.1:5001?peer=127.0.0.1:5000")
    print(f"fmu: {fmu_path}")


if __name__ == "__main__":
    raise SystemExit(main())
