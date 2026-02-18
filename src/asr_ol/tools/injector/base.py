from __future__ import annotations

from abc import ABC, abstractmethod


class Injector(ABC):
    @abstractmethod
    def inject(self, text: str) -> bool:
        raise NotImplementedError
