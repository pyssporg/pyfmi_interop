"""Role of a model interface on the wire.

The role is derived from FMI causality, not declared by the user:

* ``sender``   -- the interface has inputs only;
* ``receiver`` -- the interface has outputs only;
* ``adapter``  -- the interface has both inputs and outputs;
* ``none``     -- the interface has neither (parameters only).

A caller may narrow the derived role, never widen it: a receiver cannot be
turned into an adapter because the interface carries no inputs to send.
"""

from __future__ import annotations

from .ir import Direction, ModelDefinition

__all__ = ["ROLES", "derive_role", "resolve_role"]

#: Every legal role value, in a stable order for CLI choices.
ROLES = ("sender", "receiver", "adapter", "none")


def derive_role(model: ModelDefinition) -> str:
    """Return the role implied by ``model``'s FMI causality set."""

    has_input = any(signal.direction is Direction.INPUT for signal in model.signals)
    has_output = any(signal.direction is Direction.OUTPUT for signal in model.signals)
    if has_input and has_output:
        return "adapter"
    if has_input:
        return "sender"
    if has_output:
        return "receiver"
    return "none"


def resolve_role(model: ModelDefinition, override: str | None = None) -> str:
    """Return ``override`` if it does not widen the interface, else the derived role.

    ``override`` must be one of :data:`ROLES`.  A role widens the interface when
    it needs a causality the interface does not have; that raises
    :class:`ValueError` instead of producing a model that claims a direction it
    cannot carry.
    """

    derived = derive_role(model)
    if override is None:
        return derived
    if override not in ROLES:
        raise ValueError(
            f"unknown role {override!r}; expected one of {', '.join(ROLES)}"
        )
    has_input = any(signal.direction is Direction.INPUT for signal in model.signals)
    has_output = any(signal.direction is Direction.OUTPUT for signal in model.signals)
    needs = {
        "sender": has_input,
        "receiver": has_output,
        "adapter": has_input and has_output,
        "none": True,
    }[override]
    if not needs:
        raise ValueError(
            f"role {override!r} widens the interface; the derived role is "
            f"{derived!r}"
        )
    return override
