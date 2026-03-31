from abc import ABC

from voxkeep.shared.interfaces import ASREngine
from voxkeep.shared.interfaces import AudioSource
from voxkeep.shared.events import (
    AsrFinalEvent,
    CaptureCommand,
    RawAudioChunk,
    StorageRecord,
    VadEvent,
    WakeEvent,
)
from voxkeep.modules.injection.infrastructure.base import Injector


def test_core_boundaries_are_abstract():
    assert issubclass(AudioSource, ABC)
    assert issubclass(ASREngine, ABC)
    assert issubclass(Injector, ABC)


def test_event_shapes():
    chunk = RawAudioChunk(data=b"x", frames=160, sample_rate=16000, channels=1, ts=1.0)
    wake = WakeEvent(ts=1.1, score=0.8, keyword="ok")
    vad = VadEvent(ts=1.2, event_type="speech_start", score=0.9)
    asr = AsrFinalEvent(segment_id="1", text="hi", start_ts=1.2, end_ts=1.3)
    cap = CaptureCommand(
        session_id=1,
        keyword="alexa",
        action="inject_text",
        text="hi",
        start_ts=1.2,
        end_ts=1.3,
    )
    rec = StorageRecord(
        source="stream", text="hi", start_ts=1.2, end_ts=1.3, is_final=True, created_at=""
    )

    assert chunk.frames == 160
    assert wake.keyword == "ok"
    assert vad.event_type == "speech_start"
    assert asr.is_final is True
    assert cap.session_id == 1
    assert rec.source == "stream"
