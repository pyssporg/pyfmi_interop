"""SysML v2 ingestion: one parse, one specification, one source handle."""

from __future__ import annotations

from .generate import generate_adapter
from .parse import (
    DEFAULT_STEP_SIZE_S,
    DEFAULT_STRING_CAPACITY,
    ParsedModel,
    load_architecture,
    load_model,
    model_from_architecture,
    parse,
)

__all__ = [
    "DEFAULT_STEP_SIZE_S",
    "DEFAULT_STRING_CAPACITY",
    "ParsedModel",
    "generate_adapter",
    "load_architecture",
    "load_model",
    "model_from_architecture",
    "parse",
]
