"""Shared queue helpers re-export shim for stage-one migration."""

from asr_ol.core.queue_utils import put_nowait_or_drop

__all__ = ["put_nowait_or_drop"]
