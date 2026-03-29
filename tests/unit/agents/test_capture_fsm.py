import pytest

from asr_ol.modules.capture.domain.capture_fsm import CaptureFSM, CaptureState
from asr_ol.core.events import VadEvent, WakeEvent


def test_capture_fsm_returns_capture_window_on_speech_end():
    fsm = CaptureFSM(pre_roll_ms=200, armed_timeout_ms=1000)

    fsm.on_wake(WakeEvent(ts=10.0, score=0.8, keyword="hey_jarvis"))
    assert fsm.state == CaptureState.ARMED

    assert fsm.on_vad(VadEvent(ts=10.2, event_type="speech_start", score=0.9)) is None
    window = fsm.on_vad(VadEvent(ts=10.9, event_type="speech_end", score=0.1))

    assert window is not None
    assert window.keyword == "hey_jarvis"
    assert window.start_ts == 10.0
    assert window.end_ts == 10.9
    assert fsm.state == CaptureState.IDLE


def test_repeated_wake_refreshes_window_and_emits_once():
    fsm = CaptureFSM(pre_roll_ms=100, armed_timeout_ms=1000)
    fsm.on_wake(WakeEvent(ts=1.0, score=0.9, keyword="alexa"))
    fsm.on_wake(WakeEvent(ts=1.1, score=0.9, keyword="alexa"))
    fsm.on_vad(VadEvent(ts=1.2, event_type="speech_start", score=0.8))
    window = fsm.on_vad(VadEvent(ts=1.8, event_type="speech_end", score=0.1))

    assert window is not None
    assert window.keyword == "alexa"
    assert window.start_ts == pytest.approx(1.1)
    assert window.end_ts == 1.8


def test_armed_timeout_resets_to_idle():
    fsm = CaptureFSM(pre_roll_ms=100, armed_timeout_ms=500)
    fsm.on_wake(WakeEvent(ts=1.0, score=0.9, keyword="alexa"))

    fsm.tick(now=1.6)

    assert fsm.state == CaptureState.IDLE


def test_invalid_vad_sequence_does_not_emit_window():
    fsm = CaptureFSM(pre_roll_ms=100, armed_timeout_ms=1000)

    assert fsm.on_vad(VadEvent(ts=1.0, event_type="speech_end", score=0.1)) is None
    fsm.on_wake(WakeEvent(ts=1.2, score=0.9, keyword="alexa"))
    assert fsm.on_vad(VadEvent(ts=1.3, event_type="speech_end", score=0.1)) is None
    assert fsm.state == CaptureState.ARMED
