from __future__ import annotations

from voxkeep.shared.asr_backends import BUILTIN_BACKENDS
from voxkeep.shared.asr_backends import resolve_backend_definition


def test_builtin_registry_contains_qwen_vllm() -> None:
    assert "qwen_vllm" in BUILTIN_BACKENDS
    backend = resolve_backend_definition("qwen_vllm")

    assert backend.kind == "external_service"
    assert backend.transport == "websocket"
