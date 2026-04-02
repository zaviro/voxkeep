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
    funasr_host: str
    funasr_port: int
    funasr_path: str
    funasr_use_ssl: bool
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
    asr_backend: str = "funasr_ws_external"
    asr_mode: str = "auto"
    asr_external_host: str = "127.0.0.1"
    asr_external_port: int = 10096
    asr_external_path: str = "/"
    asr_external_use_ssl: bool = False
    asr_managed_provider: str = "docker"
    asr_managed_image: str = (
        "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13"
    )
    asr_managed_service_name: str = "funasr"
    asr_managed_expose_port: int = 10096
    asr_managed_models_dir: str = "~/.local/share/voxkeep/models/funasr"
    _asr_snapshot: tuple[str, int, str, bool] = field(
        default=_DEFAULT_ASR_EXTERNAL,
        repr=False,
        compare=False,
    )
    _asr_source: str = field(default="legacy", repr=False, compare=False)
    _reconnect_snapshot: tuple[float, float] = field(
        default=_DEFAULT_ASR_RECONNECT,
        repr=False,
        compare=False,
    )
    _reconnect_source: str = field(default="legacy", repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate configuration values after dataclass construction."""
        _require_positive_int("sample_rate", self.sample_rate)
        _require_positive_int("channels", self.channels)
        _require_positive_int("frame_ms", self.frame_ms)
        _require_positive_int("max_queue_size", self.max_queue_size)
        _require_positive_int("funasr_port", self.funasr_port)
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
        backend = self.asr_backend.strip().lower()
        object.__setattr__(self, "asr_backend", backend)
        resolve_backend_definition(backend)
        asr_mode = self.asr_mode.strip().lower()
        object.__setattr__(self, "asr_mode", asr_mode)
        if asr_mode not in {"auto", "external", "managed"}:
            raise ValueError("asr_mode must be one of: auto, external, managed")
        source = _resolve_asr_source(
            snapshot=self._asr_snapshot,
            legacy=(self.funasr_host, self.funasr_port, self.funasr_path, self.funasr_use_ssl),
            external=(
                self.asr_external_host,
                self.asr_external_port,
                self.asr_external_path,
                self.asr_external_use_ssl,
            ),
            current_source=self._asr_source,
        )
        if source == "external":
            object.__setattr__(self, "funasr_host", self.asr_external_host)
            object.__setattr__(self, "funasr_port", self.asr_external_port)
            object.__setattr__(self, "funasr_path", self.asr_external_path)
            object.__setattr__(self, "funasr_use_ssl", self.asr_external_use_ssl)
        else:
            object.__setattr__(self, "asr_external_host", self.funasr_host)
            object.__setattr__(self, "asr_external_port", self.funasr_port)
            object.__setattr__(self, "asr_external_path", self.funasr_path)
            object.__setattr__(self, "asr_external_use_ssl", self.funasr_use_ssl)
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
        object.__setattr__(self, "_asr_source", source)
        reconnect_source = _resolve_reconnect_source(
            snapshot=self._reconnect_snapshot,
            legacy=(self.asr_reconnect_initial_s, self.asr_reconnect_max_s),
            runtime=(
                self.asr_runtime_reconnect_initial_s,
                self.asr_runtime_reconnect_max_s,
            ),
            current_source=self._reconnect_source,
        )
        if reconnect_source == "runtime":
            object.__setattr__(
                self, "asr_reconnect_initial_s", self.asr_runtime_reconnect_initial_s
            )
            object.__setattr__(self, "asr_reconnect_max_s", self.asr_runtime_reconnect_max_s)
        else:
            object.__setattr__(
                self, "asr_runtime_reconnect_initial_s", self.asr_reconnect_initial_s
            )
            object.__setattr__(self, "asr_runtime_reconnect_max_s", self.asr_reconnect_max_s)
        object.__setattr__(
            self,
            "_reconnect_snapshot",
            (self.asr_reconnect_initial_s, self.asr_reconnect_max_s),
        )
        object.__setattr__(self, "_reconnect_source", reconnect_source)
        if self.asr_reconnect_max_s < self.asr_reconnect_initial_s:
            raise ValueError("asr_reconnect_max_s must be >= asr_reconnect_initial_s")
        if self.asr_runtime_reconnect_max_s < self.asr_runtime_reconnect_initial_s:
            raise ValueError(
                "asr_runtime_reconnect_max_s must be >= asr_runtime_reconnect_initial_s"
            )
        path_name = "asr_external_path" if source == "external" else "funasr_path"
        port_name = "asr_external_port" if source == "external" else "funasr_port"
        if not self.asr_external_path.startswith("/"):
            raise ValueError(f"{path_name} must start with '/'")
        _require_positive_int(port_name, self.asr_external_port)
        if not self.asr_managed_provider.strip():
            raise ValueError("asr_managed_provider must not be empty")
        if not self.asr_managed_image.strip():
            raise ValueError("asr_managed_image must not be empty")
        if not self.asr_managed_service_name.strip():
            raise ValueError("asr_managed_service_name must not be empty")
        _require_positive_int("asr_managed_expose_port", self.asr_managed_expose_port)
        if not self.asr_managed_models_dir.strip():
            raise ValueError("asr_managed_models_dir must not be empty")
        if not self.funasr_path.startswith("/"):
            raise ValueError("funasr_path must start with '/'")
        backend = self.injector_backend.strip().lower()
        if backend not in {"auto", "xdotool", "ydotool"}:
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
        backend = resolve_backend_definition(self.asr_backend)
        if backend.kind == "managed_service":
            return f"ws://127.0.0.1:{self.asr_managed_expose_port}{self.asr_external_path}"
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


def _resolve_asr_source(
    *,
    snapshot: tuple[str, int, str, bool],
    legacy: tuple[str, int, str, bool],
    external: tuple[str, int, str, bool],
    current_source: str,
) -> str:
    """Pick the authoritative ASR side for the current object state."""
    if external != snapshot and legacy == snapshot:
        return "external"
    if legacy != snapshot and external == snapshot:
        return "legacy"
    if external == legacy:
        return current_source if current_source in {"legacy", "external"} else "legacy"
    if legacy == _DEFAULT_ASR_EXTERNAL and external != _DEFAULT_ASR_EXTERNAL:
        return "external"
    if external == _DEFAULT_ASR_EXTERNAL and legacy != _DEFAULT_ASR_EXTERNAL:
        return "legacy"
    return current_source if current_source in {"legacy", "external"} else "external"


def _resolve_reconnect_source(
    *,
    snapshot: tuple[float, float],
    legacy: tuple[float, float],
    runtime: tuple[float, float],
    current_source: str,
) -> str:
    """Pick the authoritative reconnect-policy side for the current object state."""
    if runtime != snapshot and legacy == snapshot:
        return "runtime"
    if legacy != snapshot and runtime == snapshot:
        return "legacy"
    if runtime != snapshot and legacy != snapshot:
        if runtime == legacy:
            return current_source if current_source in {"legacy", "runtime"} else "runtime"
        return "runtime"
    if runtime == legacy:
        return current_source if current_source in {"legacy", "runtime"} else "legacy"
    if legacy == _DEFAULT_ASR_RECONNECT and runtime != _DEFAULT_ASR_RECONNECT:
        return "runtime"
    if runtime == _DEFAULT_ASR_RECONNECT and legacy != _DEFAULT_ASR_RECONNECT:
        return "legacy"
    return current_source if current_source in {"legacy", "runtime"} else "runtime"


__all__ = ["AppConfig", "WakeRuleConfig"]
