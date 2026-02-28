from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time

from asr_ol.core.events import VadEvent, WakeEvent


class CaptureState(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    CAPTURING = "CAPTURING"
    FINALIZING = "FINALIZING"


@dataclass(slots=True)
class _CaptureSession:
    session_id: int
    keyword: str
    wake_ts: float
    speech_start_ts: float | None = None
    speech_end_ts: float | None = None


@dataclass(slots=True, frozen=True)
class CaptureWindow:
    session_id: int
    keyword: str
    start_ts: float
    end_ts: float


class CaptureFSM:
    """Manage wake-triggered one-sentence capture and one-shot injection."""

    def __init__(self, pre_roll_ms: int, armed_timeout_ms: int) -> None:
        self._state: CaptureState = CaptureState.IDLE
        self._pre_roll_s = pre_roll_ms / 1000.0
        self._armed_timeout_s = armed_timeout_ms / 1000.0
        self._session_seq = 0
        self._session: _CaptureSession | None = None
        self._armed_deadline: float | None = None

    @property
    def state(self) -> CaptureState:
        return self._state

    def on_wake(self, event: WakeEvent) -> None:
        if self._state == CaptureState.IDLE:
            self._session_seq += 1
            self._session = _CaptureSession(
                session_id=self._session_seq,
                keyword=event.keyword,
                wake_ts=event.ts,
            )
            self._armed_deadline = event.ts + self._armed_timeout_s
            self._state = CaptureState.ARMED
            return

        # Robust against repeated wake while already armed/capturing: refresh deadline only.
        if self._state in (CaptureState.ARMED, CaptureState.CAPTURING):
            self._armed_deadline = event.ts + self._armed_timeout_s

    def on_vad(self, event: VadEvent) -> CaptureWindow | None:
        now = event.ts
        self._check_arm_timeout(now)

        if self._state == CaptureState.ARMED and event.event_type == "speech_start":
            if self._session is None:
                return None
            self._session.speech_start_ts = event.ts
            self._state = CaptureState.CAPTURING
            return None

        if self._state == CaptureState.CAPTURING and event.event_type == "speech_end":
            if self._session is None:
                return None
            self._session.speech_end_ts = event.ts
            self._state = CaptureState.FINALIZING
            command = self._finalize()
            self._reset_to_idle()
            return command

        return None

    def tick(self, now: float | None = None) -> None:
        self._check_arm_timeout(time.time() if now is None else now)

    def _check_arm_timeout(self, now: float) -> None:
        if self._state != CaptureState.ARMED:
            return
        if self._armed_deadline is not None and now >= self._armed_deadline:
            self._reset_to_idle()

    def _finalize(self) -> CaptureWindow | None:
        if self._session is None:
            return None

        start = self._session.speech_start_ts
        end = self._session.speech_end_ts
        if start is None or end is None:
            return None

        capture_start = start - self._pre_roll_s
        return CaptureWindow(
            session_id=self._session.session_id,
            keyword=self._session.keyword,
            start_ts=capture_start,
            end_ts=end,
        )

    def _reset_to_idle(self) -> None:
        self._state = CaptureState.IDLE
        self._session = None
        self._armed_deadline = None
