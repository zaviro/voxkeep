from __future__ import annotations

import sys
import types

import numpy as np

from voxkeep.modules.capture.infrastructure.silero_worker import (
    EnergyVadScorer,
    SileroVadScorer,
    _extract_score,
)


def _frame(values: list[float] | None = None) -> object:
    pcm = np.asarray(values if values is not None else [], dtype=np.float32)
    return types.SimpleNamespace(pcm_f32=pcm, sample_rate=16000)


def test_energy_vad_scorer_returns_zero_for_empty_frame() -> None:
    scorer = EnergyVadScorer()

    assert scorer.speech_score(_frame()) == 0.0


def test_energy_vad_scorer_scales_energy_and_caps_at_one() -> None:
    scorer = EnergyVadScorer()

    assert scorer.speech_score(_frame([1.0, 1.0, 1.0])) == 1.0


def test_silero_vad_try_create_falls_back_when_import_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "voxkeep.modules.capture.infrastructure.silero_worker.import_module",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
    )

    scorer = SileroVadScorer.try_create()

    assert isinstance(scorer, EnergyVadScorer)


def test_silero_vad_try_create_falls_back_when_model_init_fails(monkeypatch) -> None:
    fake_torch = types.ModuleType("torch")
    fake_torch.from_numpy = lambda value: value
    fake_silero = types.ModuleType("silero_vad")

    def load_silero_vad() -> object:
        raise RuntimeError("boom")

    fake_silero.load_silero_vad = load_silero_vad  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "silero_vad", fake_silero)

    scorer = SileroVadScorer.try_create()

    assert isinstance(scorer, EnergyVadScorer)


def test_silero_vad_speech_score_falls_back_on_predict_error() -> None:
    class FakeTorch:
        @staticmethod
        def from_numpy(value: np.ndarray) -> "FakeTensor":
            return FakeTensor(value)

    class FakeTensor:
        def __init__(self, value: np.ndarray) -> None:
            self._value = value

        def dim(self) -> int:
            return 1

        def unsqueeze(self, dim: int) -> np.ndarray:
            _ = dim
            return self._value.reshape(1, -1)

    class BrokenModel:
        def __call__(self, tensor: np.ndarray, sample_rate: int) -> float:
            _ = (tensor, sample_rate)
            raise RuntimeError("boom")

    scorer = SileroVadScorer(model=BrokenModel(), torch_module=FakeTorch())

    score = scorer.speech_score(_frame([0.5, 0.5, 0.5]))

    assert score > 0.0


def test_extract_score_handles_none_number_tuple_and_tensor_like() -> None:
    class FakeScalar:
        def item(self) -> float:
            return 0.8

    assert _extract_score(None) == 0.0
    assert _extract_score(0.7) == 0.7
    assert _extract_score((0.6, 0.2)) == 0.6
    assert _extract_score(FakeScalar()) == 0.8
