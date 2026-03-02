"""Abstract interfaces for pluggable ASR backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from asr_ol.core.events import ProcessedFrame


class ASREngine(ABC):
    """Define the ASR engine lifecycle and streaming contract."""

    @abstractmethod
    def start(self) -> None:
        """Start engine resources and background I/O."""
        raise NotImplementedError

    @abstractmethod
    def submit_frame(self, frame: ProcessedFrame) -> None:
        """Submit one preprocessed audio frame for recognition."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close engine resources and flush pending work."""
        raise NotImplementedError
