"""Compile a small model without SysML.

This example imports only :mod:`pyfmi_interop.core`: it builds a ``ModelSpec``
by hand, then generates the C++, builds the native model, and packages the FMU
in one call.  Run it from the repository root after building the native
runtime::

    python examples/core/compile_model.py /tmp/pyfmi_core_demo
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out_dir",
        nargs="?",
        default="/tmp/pyfmi_core_demo",
        help="Directory for generated sources, the build tree and the FMU.",
    )
    args = parser.parse_args()

    result = compile_model(build_spec(), Path(args.out_dir))
    print(f"sources: {result.sources}")
    print(f"library: {result.library}")
    print(f"fmu:     {result.fmu}")


if __name__ == "__main__":
    main()
