"""SysML v2 ingestion: one parse, one specification, one parser-free reduction."""

from __future__ import annotations

from .adapter import adapter_from_reduction
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
    "adapter_from_reduction",
    "generate_adapter",
    "load_architecture",
    "load_model",
    "model_from_architecture",
    "parse",
]
