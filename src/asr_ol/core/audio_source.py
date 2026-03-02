"""Abstract microphone/audio input lifecycle contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AudioSource(ABC):
    """Define a start/stop interface for audio producers."""

    @abstractmethod
    def start(self) -> None:
        """Start capturing audio into the configured sink."""
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing audio and release resources."""
        raise NotImplementedError
