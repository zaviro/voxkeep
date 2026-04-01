from voxkeep.modules.capture.application.transcript_extractor import InMemoryTranscriptExtractor
from voxkeep.shared.events import AsrFinalEvent


def test_extract_returns_joined_text_for_overlap_window():
    extractor = InMemoryTranscriptExtractor(max_segments=16)
    extractor.on_asr_final(AsrFinalEvent(segment_id="a", text="hello", start_ts=10.1, end_ts=10.4))
    extractor.on_asr_final(AsrFinalEvent(segment_id="b", text="world", start_ts=10.4, end_ts=10.7))

    text = extractor.extract(start_ts=10.0, end_ts=10.8)

    assert text == "hello world"


def test_extract_ignores_outside_or_empty_segments():
    extractor = InMemoryTranscriptExtractor(max_segments=16)
    extractor.on_asr_final(AsrFinalEvent(segment_id="a", text="  ", start_ts=1.0, end_ts=1.2))
    extractor.on_asr_final(AsrFinalEvent(segment_id="b", text="inside", start_ts=2.0, end_ts=2.3))
    extractor.on_asr_final(AsrFinalEvent(segment_id="c", text="outside", start_ts=3.0, end_ts=3.4))

    text = extractor.extract(start_ts=1.9, end_ts=2.5)

    assert text == "inside"
