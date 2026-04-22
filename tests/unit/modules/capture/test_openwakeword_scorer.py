import sys
import types

import numpy as np

from voxkeep.modules.capture.infrastructure.openwakeword_worker import (
    OpenWakeWordWorker,
    WakeRuleConfig,
    NullWakeScorer,
    OpenWakeWordScorer,
    _extract_keyword_scores,
    _normalize_rules,
)


def _install_fake_openwakeword(monkeypatch, model_cls: type) -> None:
    pkg = types.ModuleType("openwakeword")
    pkg.__path__ = []  # type: ignore[attr-defined]
    model_mod = types.ModuleType("openwakeword.model")
    model_mod.Model = model_cls
    monkeypatch.setitem(sys.modules, "openwakeword", pkg)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_mod)


def test_try_create_uses_onnx_framework(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.delenv("VOXKEEP_WAKE_MODEL", raising=False)

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
    monkeypatch.setenv("VOXKEEP_WAKE_MODEL", "hey_jarvis")

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


def test_try_create_falls_back_to_null_scorer_on_import_error(monkeypatch):
    monkeypatch.setattr(
        "voxkeep.modules.capture.infrastructure.openwakeword_worker.import_module",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
    )

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


def test_extract_keyword_scores_from_dict_payload() -> None:
    scores = _extract_keyword_scores(
        {"alexa": np.array([0.4]), "hey_jarvis": np.array([0.9])},
        ["alexa", "hey_jarvis"],
    )

    assert scores == {"alexa": 0.4, "hey_jarvis": 0.9}


def test_extract_keyword_scores_from_scalar_single_model() -> None:
    scores = _extract_keyword_scores(0.7, ["alexa"])

    assert scores == {"alexa": 0.7}


def test_extract_keyword_scores_returns_zeroes_for_multi_model_scalar_payload() -> None:
    scores = _extract_keyword_scores(0.7, ["alexa", "hey_jarvis"])

    assert scores == {"alexa": 0.0, "hey_jarvis": 0.0}


def test_normalize_rules_filters_disabled_and_empty_keyword_rules() -> None:
    rules = _normalize_rules(
        [
            {"keyword": "", "enabled": True, "threshold": 0.5, "action": "inject_text"},
            {"keyword": "alexa", "enabled": False, "threshold": 0.5, "action": "inject_text"},
            {"keyword": "hey_jarvis", "enabled": True, "threshold": 0.6, "action": "openclaw"},
        ]
    )

    assert rules == (
        WakeRuleConfig(
            keyword="hey_jarvis",
            enabled=True,
            threshold=0.6,
            action="openclaw",
        ),
    )


def test_worker_with_no_enabled_rules_emits_nothing() -> None:
    worker = OpenWakeWordWorker(
        in_queue=__import__("queue").Queue(),
        out_queue=__import__("queue").Queue(),
        stop_event=__import__("threading").Event(),
        rules=[{"keyword": "alexa", "enabled": False, "threshold": 0.5, "action": "inject_text"}],
    )

    event = worker._detect(
        types.SimpleNamespace(
            pcm_f32=np.zeros(160, dtype=np.float32),
            ts_end=1.0,
        )
    )

    assert event is None
