"""Public model specification and generation configuration.

``ModelSpec`` is the public interface a caller hands to the generator: names,
types, directions, timing and the metadata the wire plane needs.  The
composition layer is the producer of a ``ModelSpec``; the generator does not
parse a source dialect.

``BuildConfig`` carries the choices that belong to a generation run rather than
to the interface itself: the serialization backend, the wire role and the
adapter prefix.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .ir import ModelDefinition, RateGroup, Signal, deterministic_guid

__all__ = ["BuildConfig", "ModelSpec"]


@dataclass(frozen=True)
class BuildConfig:
    """Generation choices only; no model content."""

    serialization: str = "protobuf"
    role: str | None = None  # None = derive from causality
    prefix: str | None = None  # adapter naming override, ignored by the interop facade


@dataclass(frozen=True)
class ModelSpec:
    """The interface of one model, independent of how it was authored."""

    name: str
    signals: tuple[Signal, ...] = ()
    step_size_s: float | None = None
    realtime: bool = True
    interface: str | None = None
    description: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)
    rate_groups: tuple[RateGroup, ...] = ()
    #: Deterministic uuid5 of ``name`` when the caller does not pin an identity.
    guid: str | None = None

    def __post_init__(self) -> None:
        if self.guid is None:
            object.__setattr__(self, "guid", deterministic_guid(self.name))

    def to_model(self, config: BuildConfig | None = None) -> ModelDefinition:
        """Project this specification onto the generator's IR."""

        options = config or BuildConfig()
        return ModelDefinition(
            name=self.name,
            guid=self.guid,
            step_size_s=self.step_size_s,
            realtime=self.realtime,
            signals=self.signals,
            rate_groups=self.rate_groups,
            metadata=self.metadata,
            description=self.description,
            interface=self.interface,
            role=options.role,
            serialization=options.serialization,
        )

    def validate(self) -> None:
        """Raise :class:`ValueError` if the projected model is not executable."""

        self.to_model()
