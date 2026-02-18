from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import time

from asr_ol.core.events import AsrFinalEvent, CaptureCommand, VadEvent, WakeEvent


class CaptureState(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    CAPTURING = "CAPTURING"
    FINALIZING = "FINALIZING"


@dataclass(slots=True)
class CaptureWindow:
    session_id: int
    wake_ts: float
    speech_start_ts: float | None = None
    speech_end_ts: float | None = None
    injected_once: bool = False


class CaptureFSM:
    """Manage wake-triggered one-sentence capture and one-shot injection."""

    def __init__(self, pre_roll_ms: int, armed_timeout_ms: int) -> None:
        self._state: CaptureState = CaptureState.IDLE
        self._pre_roll_s = pre_roll_ms / 1000.0
        self._armed_timeout_s = armed_timeout_ms / 1000.0
        self._session_seq = 0
        self._window: CaptureWindow | None = None
        self._armed_deadline: float | None = None
        self._asr_finals: deque[AsrFinalEvent] = deque(maxlen=4096)

    @property
    def state(self) -> CaptureState:
        return self._state

    def on_asr_final(self, event: AsrFinalEvent) -> None:
        if event.is_final:
            self._asr_finals.append(event)

    def on_wake(self, event: WakeEvent) -> None:
        if self._state == CaptureState.IDLE:
            self._session_seq += 1
            self._window = CaptureWindow(session_id=self._session_seq, wake_ts=event.ts)
            self._armed_deadline = event.ts + self._armed_timeout_s
            self._state = CaptureState.ARMED
            return

        # Robust against repeated wake while already armed/capturing: refresh deadline only.
        if self._state in (CaptureState.ARMED, CaptureState.CAPTURING):
            self._armed_deadline = event.ts + self._armed_timeout_s

    def on_vad(self, event: VadEvent) -> CaptureCommand | None:
        now = event.ts
        self._check_arm_timeout(now)

        if self._state == CaptureState.ARMED and event.event_type == "speech_start":
            if self._window is None:
                return None
            self._window.speech_start_ts = event.ts
            self._state = CaptureState.CAPTURING
            return None

        if self._state == CaptureState.CAPTURING and event.event_type == "speech_end":
            if self._window is None:
                return None
            self._window.speech_end_ts = event.ts
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

    def _finalize(self) -> CaptureCommand | None:
        if self._window is None:
            return None

        start = self._window.speech_start_ts
        end = self._window.speech_end_ts
        if start is None or end is None:
            return None
        if self._window.injected_once:
            return None

        capture_start = start - self._pre_roll_s
        texts: list[str] = []
        for seg in self._asr_finals:
            if seg.end_ts < capture_start:
                continue
            if seg.start_ts > end:
                continue
            cleaned = seg.text.strip()
            if cleaned:
                texts.append(cleaned)

        final_text = " ".join(texts).strip()
        if not final_text:
            return None

        self._window.injected_once = True
        return CaptureCommand(
            session_id=self._window.session_id,
            text=final_text,
            start_ts=capture_start,
            end_ts=end,
        )

    def _reset_to_idle(self) -> None:
        self._state = CaptureState.IDLE
        self._window = None
        self._armed_deadline = None
