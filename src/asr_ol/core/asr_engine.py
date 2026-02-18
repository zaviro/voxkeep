from __future__ import annotations

from abc import ABC, abstractmethod

from asr_ol.core.events import ProcessedFrame


class ASREngine(ABC):
    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def submit_frame(self, frame: ProcessedFrame) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
