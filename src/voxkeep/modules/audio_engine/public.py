"""Public entrypoints for the audio engine module."""

from __future__ import annotations

from typing import Protocol

from voxkeep.modules.audio_engine.contracts import RuntimeStatus


class AudioEngineModule(Protocol):
    """Public API exposed by the audio engine module."""

    def start(self) -> None:
        """Start runtime resources."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop runtime resources."""
        raise NotImplementedError

    def status(self) -> RuntimeStatus:
        """Return current runtime status summary."""
        raise NotImplementedError
