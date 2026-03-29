"""Capture execution helpers for the injection module."""

from __future__ import annotations

from asr_ol.core.events import CaptureCommand
from asr_ol.modules.injection.contracts import InjectionResult
from asr_ol.shared.types import CaptureCompleted


def to_capture_command(event: CaptureCompleted) -> CaptureCommand:
    """Convert one public capture event into the legacy command shape."""
    return CaptureCommand(
        session_id=event.session_id,
        keyword=event.keyword,
        action=event.action,
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
    )


def to_result(action: str, ok: bool) -> InjectionResult:
    """Build a stable injection result."""
    return InjectionResult(ok=ok, action=action)
