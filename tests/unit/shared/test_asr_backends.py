from __future__ import annotations

from voxkeep.shared.asr_backends import BUILTIN_BACKENDS
from voxkeep.shared.asr_backends import resolve_backend_definition


def test_builtin_registry_contains_funasr_external_and_managed() -> None:
    assert "funasr_ws_external" in BUILTIN_BACKENDS
    assert "funasr_ws_managed" in BUILTIN_BACKENDS
    assert resolve_backend_definition("funasr_ws_external").transport == "websocket"


def test_builtin_registry_contains_qwen_vllm() -> None:
    backend = resolve_backend_definition("qwen_vllm")

    assert backend.kind == "external_service"
    assert backend.transport == "websocket"
