"""Normalized ASR backend health helpers."""

from __future__ import annotations

from dataclasses import dataclass


_HEALTH_STATE_ALIASES: dict[str, str] = {
    "healthy": "healthy",
    "ok": "healthy",
    "ready": "healthy",
    "starting": "starting",
    "booting": "starting",
    "initializing": "starting",
    "degraded": "degraded",
    "warning": "degraded",
    "unavailable": "unavailable",
    "down": "unavailable",
    "offline": "unavailable",
}

_ASSET_STATUS_ALIASES: dict[str, str] = {
    "ok": "ok",
    "present": "ok",
    "installed": "ok",
    "missing": "missing",
    "absent": "missing",
    "invalid": "invalid",
    "malformed": "invalid",
    "corrupt": "invalid",
}


@dataclass(slots=True, frozen=True)
class AsrHealthStatus:
    """Canonical backend health classification."""

    state: str
    reason: str
    detail: str


def probe_websocket_handshake(url: str) -> tuple[bool, bool, str]:
    """Attempt a real WebSocket handshake against ``url``.

    Returns:
        A tuple of ``(tcp_ok, handshake_ok, detail)``.
    """
    try:
        from websockets.sync.client import connect
    except Exception as exc:  # pragma: no cover - dependency failure is environmental
        return False, False, f"websockets import failed: {type(exc).__name__}: {exc}"

    try:
        with connect(url, open_timeout=1.5, proxy=None):
            pass
    except OSError as exc:
        return False, False, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return True, False, f"{type(exc).__name__}: {exc}"
    return True, True, f"websocket handshake ok: {url}"


def normalize_health_state(state: str) -> str:
    """Map a backend health label to VoxKeep's canonical state."""
    normalized = state.strip().lower()
    try:
        return _HEALTH_STATE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported health state: {state}") from exc


def normalize_asset_status(status: str) -> str:
    """Map an asset installation label to a canonical status."""
    normalized = status.strip().lower()
    try:
        return _ASSET_STATUS_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported asset status: {status}") from exc


def classify_backend_health(
    *,
    tcp_ok: bool,
    handshake_ok: bool | None,
    assets_status: str,
    detail: str,
) -> AsrHealthStatus:
    """Classify a backend probe into a normalized health status."""
    normalized_assets_status = normalize_asset_status(assets_status)
    if normalized_assets_status == "missing":
        return AsrHealthStatus(
            state=normalize_health_state("unavailable"),
            reason="assets_missing",
            detail=detail,
        )
    if normalized_assets_status == "invalid":
        return AsrHealthStatus(
            state=normalize_health_state("unavailable"),
            reason="assets_invalid",
            detail=detail,
        )
    if not tcp_ok:
        return AsrHealthStatus(
            state=normalize_health_state("unavailable"),
            reason="tcp_unreachable",
            detail=detail,
        )
    if handshake_ok is None:
        return AsrHealthStatus(
            state=normalize_health_state("starting"),
            reason="tcp_only_probe",
            detail=detail,
        )
    if not handshake_ok:
        return AsrHealthStatus(
            state=normalize_health_state("degraded"),
            reason="handshake_failed",
            detail=detail,
        )
    return AsrHealthStatus(
        state=normalize_health_state("healthy"),
        reason="ok",
        detail=detail,
    )


def classify_health_result(*, tcp_ok: bool, handshake_ok: bool, detail: str) -> AsrHealthStatus:
    """Classify a backend probe into a normalized health status."""
    return classify_backend_health(
        tcp_ok=tcp_ok,
        handshake_ok=handshake_ok,
        assets_status="ok",
        detail=detail,
    )


__all__ = [
    "AsrHealthStatus",
    "classify_backend_health",
    "classify_health_result",
    "normalize_asset_status",
    "normalize_health_state",
    "probe_websocket_handshake",
]
