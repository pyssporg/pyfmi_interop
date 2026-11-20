"""Name-to-backend registry for the serialization seam."""

from __future__ import annotations

from .base import Serialization

__all__ = ["get", "names", "register"]

_BACKENDS: dict[str, Serialization] = {}


def register(backend: Serialization, *, replace: bool = False) -> Serialization:
    """Register ``backend`` under its ``name``.

    Registering the same name twice is a programming error and raises
    :class:`ValueError`; pass ``replace=True`` only for an explicit override.
    """

    name = backend.name
    if not name:
        raise ValueError("serialization backend name must not be empty")
    if name in _BACKENDS:
        if _BACKENDS[name] is backend:
            return backend
        if not replace:
            raise ValueError(f"serialization backend already registered: {name!r}")
    _BACKENDS[name] = backend
    return backend


def get(name: str) -> Serialization:
    """Return the backend registered as ``name``.

    Unknown names raise :class:`KeyError` listing the known backends.
    """

    try:
        return _BACKENDS[name]
    except KeyError:
        known = ", ".join(sorted(_BACKENDS)) or "none"
        raise KeyError(
            f"unknown serialization backend {name!r}; known: {known}"
        ) from None


def names() -> tuple[str, ...]:
    """Return every registered backend name in registration order.

    The built-ins register as ``protobuf``, ``packed``, ``opaque`` so the CLI
    shows the canonical order.
    """

    return tuple(_BACKENDS)
