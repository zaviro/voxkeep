import sys
import types

from asr_ol.infra.wake.openwakeword_worker import NullWakeScorer, OpenWakeWordScorer


def _install_fake_openwakeword(monkeypatch, model_cls: type) -> None:
    pkg = types.ModuleType("openwakeword")
    pkg.__path__ = []  # type: ignore[attr-defined]
    model_mod = types.ModuleType("openwakeword.model")
    model_mod.Model = model_cls
    monkeypatch.setitem(sys.modules, "openwakeword", pkg)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_mod)


def test_try_create_uses_onnx_framework(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.delenv("ASR_OL_WAKE_MODEL", raising=False)

    class FakeModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    _install_fake_openwakeword(monkeypatch, FakeModel)

    scorer = OpenWakeWordScorer.try_create()

    assert isinstance(scorer, OpenWakeWordScorer)
    assert captured["inference_framework"] == "onnx"
    assert captured["wakeword_models"] == ["alexa"]


def test_try_create_respects_wake_model_env(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setenv("ASR_OL_WAKE_MODEL", "hey_jarvis")

    class FakeModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    _install_fake_openwakeword(monkeypatch, FakeModel)

    scorer = OpenWakeWordScorer.try_create()

    assert isinstance(scorer, OpenWakeWordScorer)
    assert captured["wakeword_models"] == ["hey_jarvis"]


def test_try_create_falls_back_to_null_scorer_on_init_error(monkeypatch):
    class BrokenModel:
        def __init__(self, **_kwargs):
            raise RuntimeError("boom")

    _install_fake_openwakeword(monkeypatch, BrokenModel)

    scorer = OpenWakeWordScorer.try_create()

    assert isinstance(scorer, NullWakeScorer)
