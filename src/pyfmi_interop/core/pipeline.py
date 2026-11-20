"""One model specification in, one packaged FMU out.

The pipeline owns no SysML: it generates C++ from a ``ModelSpec``, builds the
native model and packages the result.  SysML ingestion happens once, before
this module is called, in :mod:`pyfmi_interop.sysml`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .builder import build_model
from .codegen import generate_model
from .packaging import package_fmu
from .spec import BuildConfig, ModelSpec

__all__ = ["Compilation", "compile_model"]


@dataclass(frozen=True)
class Compilation:
    """Where each stage of a compilation left its artifact."""

    sources: Path
    library: Path
    fmu: Path


def compile_model(
    spec: ModelSpec,
    out_dir: str | Path,
    *,
    out_fmu: str | Path | None = None,
    build_dir: str | Path | None = None,
    config: BuildConfig | None = None,
) -> Compilation:
    """Generate, build and package ``spec`` in one call."""

    sources = generate_model(spec, out_dir, config)
    library = build_model(sources, build_dir)
    destination = (
        Path(out_fmu)
        if out_fmu is not None
        else Path(out_dir) / f"{spec.name}.fmu"
    )
    fmu = package_fmu(
        sources,
        library,
        destination,
        model=spec.to_model(config),
    )
    return Compilation(sources=Path(sources), library=Path(library), fmu=Path(fmu))
