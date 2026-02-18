from asr_ol.agents.capture_fsm import CaptureFSM, CaptureState
from asr_ol.core.events import AsrFinalEvent, VadEvent, WakeEvent


def test_capture_fsm_one_shot_injection():
    fsm = CaptureFSM(pre_roll_ms=200, armed_timeout_ms=1000)

    fsm.on_wake(WakeEvent(ts=10.0, score=0.8, keyword="wake"))
    assert fsm.state == CaptureState.ARMED

    fsm.on_asr_final(AsrFinalEvent(segment_id="a", text="hello", start_ts=10.1, end_ts=10.4))
    fsm.on_asr_final(AsrFinalEvent(segment_id="b", text="world", start_ts=10.4, end_ts=10.7))

    assert fsm.on_vad(VadEvent(ts=10.2, event_type="speech_start", score=0.9)) is None
    cmd = fsm.on_vad(VadEvent(ts=10.9, event_type="speech_end", score=0.1))

    assert cmd is not None
    assert cmd.text == "hello world"
    assert fsm.state == CaptureState.IDLE


def test_repeated_wake_does_not_duplicate_capture():
    fsm = CaptureFSM(pre_roll_ms=100, armed_timeout_ms=1000)
    fsm.on_wake(WakeEvent(ts=1.0, score=0.9, keyword="wake"))
    fsm.on_wake(WakeEvent(ts=1.1, score=0.9, keyword="wake"))
    fsm.on_asr_final(AsrFinalEvent(segment_id="a", text="once", start_ts=1.2, end_ts=1.5))
    fsm.on_vad(VadEvent(ts=1.2, event_type="speech_start", score=0.8))
    cmd = fsm.on_vad(VadEvent(ts=1.8, event_type="speech_end", score=0.1))

    assert cmd is not None
    assert cmd.text == "once"
