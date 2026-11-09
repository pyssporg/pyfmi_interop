"""C++ source generation for :mod:`pyfmi_distributed`."""

from __future__ import annotations

from .cmake import render_cmake
from .cpp import generate_model

__all__ = ["generate_model", "render_cmake"]
