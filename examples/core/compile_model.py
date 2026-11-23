"""Compile a SysML-free ``ModelSpec`` into a packaged FMI 2.0 FMU.

Run from the workspace root:

    python repos/pyfmi_interop/examples/core/compile_model.py

The sources, native library, and FMU land under ``build/examples/core/``
unless ``--out`` is given.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyfmi_interop.core import (
    DataType,
    Direction,
    ModelSpec,
    Signal,
    compile_model,
)


def build_spec() -> ModelSpec:
    """Return a two-signal interface plus one parameter."""

    return ModelSpec(
        name="core_demo",
        signals=(
            Signal("demand", 1, DataType.REAL, Direction.INPUT),
            Signal("actual", 2, DataType.REAL, Direction.OUTPUT),
            Signal("gain", 3, DataType.REAL, Direction.PARAMETER, initial=1.0),
        ),
        step_size_s=0.001,
        description="SysML-free compile_model example",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("build/examples/core"),
        help="output directory (default: build/examples/core)",
    )
    args = parser.parse_args()

    result = compile_model(build_spec(), args.out)
    print(result.sources)
    print(result.library)
    print(result.fmu)


if __name__ == "__main__":
    main()
