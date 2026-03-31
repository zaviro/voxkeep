def test_new_module_public_entrypoints_exist() -> None:
    from voxkeep.modules.capture.public import CaptureModule
    from voxkeep.modules.injection.public import InjectionModule
    from voxkeep.modules.runtime.public import RuntimeModule
    from voxkeep.modules.storage.public import StorageModule
    from voxkeep.modules.transcription.public import TranscriptionModule

    assert CaptureModule
    assert InjectionModule
    assert RuntimeModule
    assert StorageModule
    assert TranscriptionModule
