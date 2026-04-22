"""Configuration dataclasses and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from voxkeep.shared.asr_backends import resolve_backend_definition


_DEFAULT_ASR_EXTERNAL = ("127.0.0.1", 10096, "/", False)
_DEFAULT_ASR_RECONNECT = (1.0, 30.0)


@dataclass(slots=True, frozen=True)
class WakeRuleConfig:
    """Wake keyword routing rule."""

    keyword: str
    enabled: bool
    threshold: float
    action: str


@dataclass(slots=True, frozen=True)
class AudioEngineConfig:
    """Audio engine specific configuration."""

    sample_rate: int
    channels: int
    frame_ms: int
    max_queue_size: int

    @property
    def frame_samples(self) -> int:
        """Return frame size in samples."""
        return int(self.sample_rate * (self.frame_ms / 1000.0))


@dataclass(slots=True, frozen=True)
class AsrConfig:
    """ASR specific configuration."""

    backend: str
    mode: str
    external_host: str
    external_port: int
    external_path: str
    use_ssl: bool
    reconnect_initial_s: float
    reconnect_max_s: float
    runtime_reconnect_initial_s: float
    runtime_reconnect_max_s: float
    qwen_model: str
    qwen_realtime: bool
    qwen_gpu_memory_utilization: float
    qwen_max_model_len: int
    max_queue_size: int
    sample_rate: int

    @property
    def ws_url(self) -> str:
        """Return websocket endpoint URL."""
        schema = "wss" if self.use_ssl else "ws"
        return f"{schema}://{self.external_host}:{self.external_port}{self.external_path}"


@dataclass(slots=True, frozen=True)
class CaptureConfig:
    """Audio capture and VAD/Wake specific configuration."""

    wake_threshold: float
    wake_rules: tuple[WakeRuleConfig, ...]
    vad_speech_threshold: float
    vad_silence_ms: int
    pre_roll_ms: int
    armed_timeout_ms: int
    max_queue_size: int

    @property
    def enabled_wake_rules(self) -> tuple[WakeRuleConfig, ...]:
        """Return wake rules currently enabled."""
        return tuple(rule for rule in self.wake_rules if rule.enabled)


@dataclass(slots=True, frozen=True)
class StorageConfig:
    """Storage specific configuration."""

    sqlite_path: str
    store_final_only: bool
    jsonl_debug_path: str | None
    max_queue_size: int


@dataclass(slots=True, frozen=True)
class InjectorConfig:
    """Text injector specific configuration."""

    backend: str
    auto_enter: bool
    xdotool_delay_ms: int
    openclaw_command: tuple[str, ...]
    openclaw_timeout_s: float
    max_queue_size: int


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Immutable runtime configuration snapshot."""

    audio_engine: AudioEngineConfig
    asr: AsrConfig
    capture: CaptureConfig
    storage: StorageConfig
    injector: InjectorConfig
    log_level: str

    def __post_init__(self) -> None:
        """Validate configuration values after dataclass construction."""
        # Audio Engine validation
        _require_positive_int("audio_engine.sample_rate", self.audio_engine.sample_rate)
        _require_positive_int("audio_engine.channels", self.audio_engine.channels)
        _require_positive_int("audio_engine.frame_ms", self.audio_engine.frame_ms)
        _require_positive_int("audio_engine.max_queue_size", self.audio_engine.max_queue_size)

        # ASR validation
        _require_positive_float("asr.reconnect_initial_s", self.asr.reconnect_initial_s)
        _require_positive_float("asr.reconnect_max_s", self.asr.reconnect_max_s)
        _require_positive_float(
            "asr.runtime_reconnect_initial_s", self.asr.runtime_reconnect_initial_s
        )
        _require_positive_float("asr.runtime_reconnect_max_s", self.asr.runtime_reconnect_max_s)
        _require_probability(
            "asr.qwen_gpu_memory_utilization", self.asr.qwen_gpu_memory_utilization
        )
        _require_positive_int("asr.qwen_max_model_len", self.asr.qwen_max_model_len)

        backend = self.asr.backend.strip().lower()
        resolve_backend_definition(backend)

        if not self.asr.qwen_model.strip():
            raise ValueError("asr.qwen_model must not be empty")

        if self.asr.mode.strip().lower() not in {"external"}:
            raise ValueError("asr.mode must be 'external' (managed is no longer supported)")

        if self.asr.runtime_reconnect_max_s < self.asr.runtime_reconnect_initial_s:
            raise ValueError(
                "asr.runtime_reconnect_max_s must be >= asr.runtime_reconnect_initial_s"
            )

        if not self.asr.external_path.startswith("/"):
            raise ValueError("asr.external_path must start with '/'")
        _require_positive_int("asr.external_port", self.asr.external_port)

        # Capture validation
        _require_probability("capture.wake_threshold", self.capture.wake_threshold)
        _require_probability("capture.vad_speech_threshold", self.capture.vad_speech_threshold)
        _require_non_negative_int("capture.pre_roll_ms", self.capture.pre_roll_ms)
        _require_positive_int("capture.armed_timeout_ms", self.capture.armed_timeout_ms)
        _require_positive_int("capture.vad_silence_ms", self.capture.vad_silence_ms)
        _require_positive_int("capture.max_queue_size", self.capture.max_queue_size)
        _validate_wake_rules(self.capture.wake_rules)

        # Storage validation
        _require_positive_int("storage.max_queue_size", self.storage.max_queue_size)

        # Injector validation
        injector_backend = self.injector.backend.strip().lower()
        if injector_backend not in {"auto", "xdotool", "ydotool"}:
            raise ValueError("injector.backend must be one of: auto, xdotool, ydotool")
        _require_non_negative_int("injector.xdotool_delay_ms", self.injector.xdotool_delay_ms)
        _require_positive_float("injector.openclaw_timeout_s", self.injector.openclaw_timeout_s)
        _require_positive_int("injector.max_queue_size", self.injector.max_queue_size)

        if not self.injector.openclaw_command:
            raise ValueError("injector.openclaw_command must not be empty")
        if any(not part.strip() for part in self.injector.openclaw_command):
            raise ValueError("injector.openclaw_command contains empty parts")

        # Global validation
        if not self.log_level.strip():
            raise ValueError("log_level must not be empty")


def _require_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _require_non_negative_int(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _require_positive_float(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _require_probability(name: str, value: float) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _validate_wake_rules(rules: tuple[WakeRuleConfig, ...]) -> None:
    seen: set[str] = set()
    for rule in rules:
        keyword = rule.keyword.strip()
        if not keyword:
            raise ValueError("wake_rules contains empty keyword")
        if keyword in seen:
            raise ValueError(f"wake_rules contains duplicate keyword: {keyword}")
        seen.add(keyword)
        _require_probability("wake_rules.threshold", rule.threshold)
        if not rule.action.strip():
            raise ValueError(f"wake_rules[{keyword}] action must not be empty")


__all__ = ["AppConfig", "WakeRuleConfig"]
