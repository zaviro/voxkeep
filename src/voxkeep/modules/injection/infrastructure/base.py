"""Base injector contract for the injection module."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Injector(ABC):
    """Contract for text injection backends."""

    @abstractmethod
    def inject(self, text: str) -> bool:
        """Inject text into the focused target."""
        raise NotImplementedError
