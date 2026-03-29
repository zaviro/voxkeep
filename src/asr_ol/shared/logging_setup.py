"""Shared logging re-export shim for stage-one migration."""

from asr_ol.core.logging_setup import configure_logging

__all__ = ["configure_logging"]
