"""Configuration dataclasses and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

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
class AppConfig:
    """Immutable runtime configuration snapshot."""

    sample_rate: int
    channels: int
    frame_ms: int
    max_queue_size: int
    asr_reconnect_initial_s: float
    asr_reconnect_max_s: float
    wake_threshold: float
    wake_rules: tuple[WakeRuleConfig, ...]
    vad_speech_threshold: float
    vad_silence_ms: int
    pre_roll_ms: int
    armed_timeout_ms: int
    sqlite_path: str
    store_final_only: bool
    jsonl_debug_path: str | None
    injector_backend: str
    injector_auto_enter: bool
    xdotool_delay_ms: int
    openclaw_command: tuple[str, ...]
    openclaw_timeout_s: float
    log_level: str
    asr_runtime_reconnect_initial_s: float = 1.0
    asr_runtime_reconnect_max_s: float = 30.0
    asr_backend: str = "qwen_vllm"
    asr_mode: str = "external"
    asr_external_host: str = "127.0.0.1"
    asr_external_port: int = 10096
    asr_external_path: str = "/"
    asr_external_use_ssl: bool = False
    asr_qwen_model: str = "Qwen/Qwen3-ASR-1.7B"
    asr_qwen_realtime: bool = True
    asr_qwen_gpu_memory_utilization: float = 0.65
    asr_qwen_max_model_len: int = 32768
    _asr_snapshot: tuple[str, int, str, bool] = field(
        default=_DEFAULT_ASR_EXTERNAL,
        repr=False,
        compare=False,
    )
    _reconnect_snapshot: tuple[float, float] = field(
        default=_DEFAULT_ASR_RECONNECT,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Validate configuration values after dataclass construction."""
        _require_positive_int("sample_rate", self.sample_rate)
        _require_positive_int("channels", self.channels)
        _require_positive_int("frame_ms", self.frame_ms)
        _require_positive_int("max_queue_size", self.max_queue_size)
        _require_probability("wake_threshold", self.wake_threshold)
        _require_probability("vad_speech_threshold", self.vad_speech_threshold)
        _require_non_negative_int("pre_roll_ms", self.pre_roll_ms)
        _require_positive_int("armed_timeout_ms", self.armed_timeout_ms)
        _require_positive_int("vad_silence_ms", self.vad_silence_ms)
        _require_positive_float("asr_reconnect_initial_s", self.asr_reconnect_initial_s)
        _require_positive_float("asr_reconnect_max_s", self.asr_reconnect_max_s)
        _require_positive_float(
            "asr_runtime_reconnect_initial_s",
            self.asr_runtime_reconnect_initial_s,
        )
        _require_positive_float("asr_runtime_reconnect_max_s", self.asr_runtime_reconnect_max_s)
        _require_probability(
            "asr_qwen_gpu_memory_utilization",
            self.asr_qwen_gpu_memory_utilization,
        )
        _require_positive_int("asr_qwen_max_model_len", self.asr_qwen_max_model_len)

        backend = self.asr_backend.strip().lower()
        object.__setattr__(self, "asr_backend", backend)
        resolve_backend_definition(backend)

        if not self.asr_qwen_model.strip():
            raise ValueError("asr_qwen_model must not be empty")

        asr_mode = self.asr_mode.strip().lower()
        object.__setattr__(self, "asr_mode", asr_mode)
        if asr_mode not in {"external"}:
            raise ValueError("asr_mode must be 'external' (managed is no longer supported)")

        object.__setattr__(
            self,
            "_asr_snapshot",
            (
                self.asr_external_host,
                self.asr_external_port,
                self.asr_external_path,
                self.asr_external_use_ssl,
            ),
        )

        if self.asr_runtime_reconnect_max_s < self.asr_runtime_reconnect_initial_s:
            raise ValueError(
                "asr_runtime_reconnect_max_s must be >= asr_runtime_reconnect_initial_s"
            )

        if not self.asr_external_path.startswith("/"):
            raise ValueError("asr_external_path must start with '/'")
        _require_positive_int("asr_external_port", self.asr_external_port)

        injector_backend = self.injector_backend.strip().lower()
        if injector_backend not in {"auto", "xdotool", "ydotool"}:
            raise ValueError("injector_backend must be one of: auto, xdotool, ydotool")
        _require_non_negative_int("xdotool_delay_ms", self.xdotool_delay_ms)
        _require_positive_float("openclaw_timeout_s", self.openclaw_timeout_s)

        if not self.openclaw_command:
            raise ValueError("openclaw_command must not be empty")
        if any(not part.strip() for part in self.openclaw_command):
            raise ValueError("openclaw_command contains empty parts")
        if not self.log_level.strip():
            raise ValueError("log_level must not be empty")
        _validate_wake_rules(self.wake_rules)

    @property
    def frame_samples(self) -> int:
        """Return frame size in samples."""
        return int(self.sample_rate * (self.frame_ms / 1000.0))

    @property
    def asr_ws_url(self) -> str:
        """Return websocket endpoint URL assembled from the active ASR backend."""
        host = self.asr_external_host
        port = self.asr_external_port
        schema = "wss" if self.asr_external_use_ssl else "ws"
        return f"{schema}://{host}:{port}{self.asr_external_path}"

    @property
    def enabled_wake_rules(self) -> tuple[WakeRuleConfig, ...]:
        """Return wake rules currently enabled."""
        return tuple(rule for rule in self.wake_rules if rule.enabled)


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
