"""Public entrypoints for the runtime module."""

from __future__ import annotations

from typing import Protocol

from voxkeep.modules.runtime.contracts import RuntimeStatus


class RuntimeModule(Protocol):
    """Public API exposed by the runtime module."""

    def start(self) -> None:
        """Start runtime resources."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop runtime resources."""
        raise NotImplementedError

    def status(self) -> RuntimeStatus:
        """Return current runtime status summary."""
        raise NotImplementedError
