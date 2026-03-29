def test_new_module_public_entrypoints_exist() -> None:
    from asr_ol.modules.capture.public import CaptureModule
    from asr_ol.modules.injection.public import InjectionModule
    from asr_ol.modules.runtime.public import RuntimeModule
    from asr_ol.modules.storage.public import StorageModule
    from asr_ol.modules.transcription.public import TranscriptionModule

    assert CaptureModule
    assert InjectionModule
    assert RuntimeModule
    assert StorageModule
    assert TranscriptionModule
