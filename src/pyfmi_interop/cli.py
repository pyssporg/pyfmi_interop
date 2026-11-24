"""Command line interface for :mod:`pyfmi_interop`.

The CLI is a thin dispatcher over the public API: it parses arguments, loads
the IR, and prints the paths the Python layer produced.  Every expected failure
is reported on stderr and mapped to exit status 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .builder import build_model
from .codegen import generate_model
from .core import BuildConfig
from .ir import ModelDefinition, model_from_dict
from .packaging import package_fmu
from .roles import ROLES
from .schema import write_schema
from .serialization import names as serialization_names

__all__ = ["build_parser", "main"]

#: Byte transports shipped in ``transport/``.  The C++ registry
#: (``make_transport``/``transport_names``) is authoritative at run time; this
#: list is the operator-facing view and must match it.
_BYTE_TRANSPORTS = ("loopback", "udp", "tcp", "unix")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfmi-interop",
        description="Generate, build and package realtime FMI runtimes.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("transports", help="List the byte transport names.")
    subparsers.add_parser(
        "serializations",
        help="List the payload serialization backends.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Summarise a model.json IR file.",
    )
    inspect_parser.add_argument("--model-json", type=Path, required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate the C++ source tree for a model.",
    )
    generate_parser.add_argument(
        "--model-json",
        type=Path,
        required=True,
        help="Path to a model.json IR file.",
    )
    generate_parser.add_argument("--out", type=Path, required=True)
    generate_parser.add_argument(
        "--serialization",
        choices=serialization_names(),
        default="protobuf",
        help="Payload serialization backend (default: protobuf).",
    )
    generate_parser.add_argument(
        "--role",
        choices=ROLES,
        default=None,
        help="Narrow the role derived from FMI causality.",
    )
    build_parser_ = subparsers.add_parser(
        "build",
        help="Build a generated model source tree.",
    )
    build_parser_.add_argument("model_dir", type=Path)
    build_parser_.add_argument("--build-dir", type=Path, default=None)

    package_parser = subparsers.add_parser(
        "package",
        help="Package a built model into an .fmu archive.",
    )
    package_parser.add_argument("model_dir", type=Path)
    package_parser.add_argument("--library", type=Path, required=True)
    package_parser.add_argument("--out", type=Path, required=True)

    schema_parser = subparsers.add_parser(
        "schema",
        help="Emit the wire schema bundle for a model.json IR file.",
    )
    schema_parser.add_argument("--model-json", type=Path, required=True)
    schema_parser.add_argument("--out", type=Path, required=True)
    schema_parser.add_argument(
        "--serialization",
        choices=serialization_names(),
        default="protobuf",
        help="Payload serialization backend (default: protobuf).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(parser, args)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.command == "transports":
        _print_transports()
        return 0
    if args.command == "serializations":
        _print_serializations()
        return 0
    if args.command == "inspect":
        _print_model(_load_model_json(args.model_json))
        return 0
    if args.command == "generate":
        model = _load_model_json(args.model_json)
        target = generate_model(
            model,
            args.out,
            BuildConfig(serialization=args.serialization, role=args.role),
        )
        print(f"Generated model sources at {target}")
        return 0
    if args.command == "build":
        library = build_model(args.model_dir, args.build_dir)
        print(f"Built {library}")
        return 0
    if args.command == "package":
        destination = package_fmu(args.model_dir, args.library, args.out)
        print(f"Packaged {destination}")
        return 0
    if args.command == "schema":
        paths = write_schema(
            _load_model_json(args.model_json),
            args.out,
            serialization=args.serialization,
        )
        descriptor = next(path for path in paths if path.name == "wire.json")
        if args.serialization == "protobuf":
            proto_path = next(path for path in paths if path.suffix == ".proto")
            print(f"Schema proto at {proto_path}")
        print(f"Schema descriptor at {descriptor}")
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


def _load_model_json(path: Path) -> ModelDefinition:
    if not path.is_file():
        raise FileNotFoundError(f"model JSON does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return model_from_dict(payload)


def _print_transports() -> None:
    print("name")
    for name in _BYTE_TRANSPORTS:
        print(name)


def _print_serializations() -> None:
    print("name")
    for name in serialization_names():
        print(name)


def _print_model(model: ModelDefinition) -> None:
    print(f"model: {model.name}")
    print(f"guid: {model.guid}")
    print(f"step_size_s: {model.step_size_s!r}")
    print(f"realtime: {'true' if model.realtime else 'false'}")
    if model.description:
        print(f"description: {model.description}")
    if model.interface:
        print(f"interface: {model.interface}")
    if model.role:
        print(f"role: {model.role}")
    if model.serialization:
        print(f"serialization: {model.serialization}")
    print(f"signals: {len(model.signals)}")
    for signal in sorted(model.signals, key=lambda item: item.value_reference):
        details = [f"{signal.data_type.value}", f"{signal.direction.value}"]
        if signal.unit:
            details.append(f"unit={signal.unit}")
        if signal.rate_hz is not None:
            details.append(f"rate_hz={signal.rate_hz!r}")
        print(
            f"  {signal.value_reference}: {signal.name} "
            f"({', '.join(details)})"
        )
    print(f"rate_groups: {len(model.rate_groups)}")
    for group in sorted(model.rate_groups, key=lambda item: item.name):
        print(
            f"  {group.name} period_s={group.period_s!r} "
            f"deadline_s={group.deadline_s!r} "
            f"signals={','.join(group.signals) or '-'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
