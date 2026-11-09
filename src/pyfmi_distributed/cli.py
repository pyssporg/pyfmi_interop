"""Command line interface for :mod:`pyfmi_distributed`.

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
from .adapters import adapter_cmake_flags, available_adapters
from .builder import build_model
from .codegen import generate_model
from .ir import ModelDefinition, model_from_dict
from .packaging import package_fmu

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfmi-distributed",
        description="Generate, build and package realtime FMI runtimes.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("adapters", help="List transport adapters.")

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Summarise a model.json IR file.",
    )
    inspect_parser.add_argument("--model-json", type=Path, required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate the C++ source tree for a model.",
    )
    source = generate_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--model-json", type=Path, help="Path to a model.json IR file.")
    source.add_argument("--sysml", type=Path, help="Path to a SysML v2 architecture file.")
    generate_parser.add_argument("--out", type=Path, required=True)
    generate_parser.add_argument(
        "--step-size",
        type=float,
        default=None,
        help="Base step size in seconds (SysML input only).",
    )
    generate_parser.add_argument(
        "--name",
        default=None,
        help="Model name override (SysML input only).",
    )

    build_parser_ = subparsers.add_parser(
        "build",
        help="Build a generated model source tree.",
    )
    build_parser_.add_argument("model_dir", type=Path)
    build_parser_.add_argument("--build-dir", type=Path, default=None)
    build_parser_.add_argument(
        "--adapter",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Enable a transport adapter gate for this build (repeatable). "
            "The matching PYFMI_DIST_ENABLE_* option is turned ON."
        ),
    )

    package_parser = subparsers.add_parser(
        "package",
        help="Package a built model into an .fmu archive.",
    )
    package_parser.add_argument("model_dir", type=Path)
    package_parser.add_argument("--library", type=Path, required=True)
    package_parser.add_argument("--out", type=Path, required=True)

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
    if args.command == "adapters":
        _print_adapters()
        return 0
    if args.command == "inspect":
        _print_model(_load_model_json(args.model_json))
        return 0
    if args.command == "generate":
        model = (
            _load_model_json(args.model_json)
            if args.model_json is not None
            else _model_from_sysml(args.sysml, args.step_size, args.name)
        )
        target = generate_model(model, args.out)
        print(f"Generated model sources at {target}")
        return 0
    if args.command == "build":
        cmake_args = adapter_cmake_flags(args.adapter)
        library = build_model(args.model_dir, args.build_dir, cmake_args=cmake_args)
        print(f"Built {library}")
        return 0
    if args.command == "package":
        destination = package_fmu(args.model_dir, args.library, args.out)
        print(f"Packaged {destination}")
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


def _load_model_json(path: Path) -> ModelDefinition:
    if not path.is_file():
        raise FileNotFoundError(f"model JSON does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return model_from_dict(payload)


def _model_from_sysml(
    path: Path,
    step_size: float | None,
    name: str | None,
) -> ModelDefinition:
    try:
        from . import sysml
    except ImportError as error:
        raise RuntimeError(
            "SysML ingestion is unavailable; install the 'sysml' extra with "
            "'pip install pyfmi-distributed[sysml]'"
        ) from error

    builder = getattr(sysml, "load_model", None)
    if builder is None:
        raise RuntimeError(
            "pyfmi_distributed.sysml does not provide load_model(); "
            "reinstall the 'sysml' extra"
        )
    return builder(path, name=name, step_size_s=step_size)


def _print_adapters() -> None:
    rows: list[tuple[str, ...]] = [
        ("name", "kind", "available", "experimental", "requires"),
    ]
    for descriptor in available_adapters():
        rows.append(
            (
                descriptor.name,
                descriptor.kind,
                "yes" if _adapter_available(descriptor.name) else "no",
                "yes" if descriptor.experimental else "no",
                ", ".join(descriptor.requires) or "-",
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    for row in rows:
        cells = [cell.ljust(widths[index]) for index, cell in enumerate(row)]
        print("  ".join(cells).rstrip())


def _adapter_available(name: str) -> bool:
    # The loopback adapter is always compiled in.  External adapters report
    # their availability from the native runtime, which the Python layer cannot
    # probe; an experimental adapter is therefore reported as unavailable here.
    return name == "loopback"


def _print_model(model: ModelDefinition) -> None:
    print(f"model: {model.name}")
    print(f"guid: {model.guid}")
    print(f"step_size_s: {model.step_size_s!r}")
    print(f"realtime: {'true' if model.realtime else 'false'}")
    if model.description:
        print(f"description: {model.description}")
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
    print(f"bindings: {len(model.bindings)}")
    for binding in sorted(
        model.bindings,
        key=lambda item: (item.signal, item.transport, item.channel),
    ):
        print(
            f"  {binding.signal} -> {binding.transport}:{binding.channel} "
            f"({binding.direction.value})"
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
