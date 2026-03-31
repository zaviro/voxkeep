"""Public contracts for the injection module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class InjectionResult:
    """Result returned by injection-side command execution."""

    ok: bool
    action: str
