"""Environment variable overrides for configuration loading."""

from __future__ import annotations


def _parse_bool(raw: str) -> bool:
    return raw.lower() in {"1", "true", "yes", "on"}


ENV_MAP = {
    "VOXKEEP_SAMPLE_RATE": ("sample_rate", int),
    "VOXKEEP_CHANNELS": ("channels", int),
    "VOXKEEP_FRAME_MS": ("frame_ms", int),
    "VOXKEEP_MAX_QUEUE_SIZE": ("max_queue_size", int),
    "VOXKEEP_ASR_BACKEND": ("asr.backend", str),
    "VOXKEEP_ASR_MODE": ("asr.mode", str),
    "VOXKEEP_ASR_EXTERNAL_HOST": ("asr.external.host", str),
    "VOXKEEP_ASR_EXTERNAL_PORT": ("asr.external.port", int),
    "VOXKEEP_ASR_EXTERNAL_PATH": ("asr.external.path", str),
    "VOXKEEP_ASR_EXTERNAL_USE_SSL": ("asr.external.use_ssl", _parse_bool),
    "VOXKEEP_ASR_RUNTIME_RECONNECT_INITIAL_S": ("asr.runtime.reconnect_initial_s", float),
    "VOXKEEP_ASR_RUNTIME_RECONNECT_MAX_S": ("asr.runtime.reconnect_max_s", float),
    "VOXKEEP_ASR_QWEN_MODEL": ("asr.qwen.model", str),
    "VOXKEEP_ASR_QWEN_REALTIME": ("asr.qwen.realtime", _parse_bool),
    "VOXKEEP_ASR_QWEN_GPU_MEMORY_UTILIZATION": (
        "asr.qwen.gpu_memory_utilization",
        float,
    ),
    "VOXKEEP_ASR_QWEN_MAX_MODEL_LEN": ("asr.qwen.max_model_len", int),
    "VOXKEEP_WAKE_THRESHOLD": ("wake.threshold", float),
    "VOXKEEP_VAD_SPEECH_THRESHOLD": ("vad.speech_threshold", float),
    "VOXKEEP_VAD_SILENCE_MS": ("vad.silence_ms", int),
    "VOXKEEP_PRE_ROLL_MS": ("capture.pre_roll_ms", int),
    "VOXKEEP_CAPTURE_ARMED_TIMEOUT_MS": ("capture.armed_timeout_ms", int),
    "VOXKEEP_SQLITE_PATH": ("storage.sqlite_path", str),
    "VOXKEEP_STORE_FINAL_ONLY": ("storage.store_final_only", _parse_bool),
    "VOXKEEP_JSONL_DEBUG_PATH": ("storage.jsonl_debug_path", str),
    "VOXKEEP_INJECTOR_BACKEND": ("injector.backend", str),
    "VOXKEEP_INJECTOR_AUTO_ENTER": ("injector.auto_enter", _parse_bool),
    "VOXKEEP_XDOTOOL_DELAY_MS": ("injector.xdotool_delay_ms", int),
    "VOXKEEP_OPENCLAW_TIMEOUT_S": ("actions.openclaw_agent.timeout_s", float),
    "VOXKEEP_LOG_LEVEL": ("runtime.log_level", str),
}


__all__ = ["ENV_MAP"]
