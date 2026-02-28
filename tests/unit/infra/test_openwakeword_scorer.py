import sys
import types

import numpy as np

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

    scorer = OpenWakeWordScorer.try_create(model_names=["alexa", "hey_jarvis"])

    assert isinstance(scorer, OpenWakeWordScorer)
    assert captured["inference_framework"] == "onnx"
    assert captured["wakeword_models"] == ["alexa", "hey_jarvis"]


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


def test_score_extracts_per_keyword_scores():
    class FakeModel:
        def predict(self, _frame):  # type: ignore[no-untyped-def]
            return {"alexa": np.array([0.2]), "hey_jarvis": np.array([0.8])}

    scorer = OpenWakeWordScorer(model=FakeModel(), model_names=["alexa", "hey_jarvis"])
    frame = types.SimpleNamespace(pcm_f32=np.zeros(160, dtype=np.float32))

    scores = scorer.score(frame)

    assert scores["alexa"] == 0.2
    assert scores["hey_jarvis"] == 0.8
