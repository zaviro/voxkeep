from __future__ import annotations

import os
import subprocess
from pathlib import Path
import threading

import pytest
from websockets.sync.server import serve

from voxkeep.shared.asr_assets import assets_state_path
from voxkeep.shared.asr_assets import read_assets_state
from voxkeep.shared.asr_assets import write_assets_state


def test_assets_state_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    write_assets_state({"funasr_ws_managed": {"installed": True}})

    assert assets_state_path().name == "installed.json"
    assert read_assets_state()["funasr_ws_managed"]["installed"] is True


def test_read_assets_state_rejects_malformed_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = assets_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed installed.json"):
        read_assets_state()


@pytest.mark.parametrize("pactl_mode", ["missing", "info_fails"])
def test_check_env_survives_pactl_absence_or_info_failure(
    tmp_path, monkeypatch, pactl_mode
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$1" = run ] && [ "$2" = --python ] && [ "$4" = python ]; then\n'
        "  shift 4\n"
        '  exec python "$@"\n'
        "fi\n"
        'exec python "$@"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)

    if pactl_mode == "info_fails":
        pactl = bin_dir / "pactl"
        pactl.write_text(
            '#!/usr/bin/env sh\nif [ "${1:-}" = list ]; then\n  exit 0\nfi\nexit 1\n',
            encoding="utf-8",
        )
        pactl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["XDG_SESSION_TYPE"] = "wayland"

    proc = subprocess.run(
        ["/bin/bash", str(Path("scripts/check_env.sh"))],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "Summary: PASS=" in proc.stdout
    assert proc.returncode != 127


def test_check_env_runs_inline_websocket_probe_even_with_malformed_assets(
    tmp_path, monkeypatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$1" = run ] && [ "$2" = --python ] && [ "$4" = python ]; then\n'
        "  shift 4\n"
        '  exec python "$@"\n'
        "fi\n"
        'exec python "$@"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)

    pactl = bin_dir / "pactl"
    pactl.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$1" = list ] && [ "$2" = short ] && [ "$3" = sources ]; then\n'
        "  printf '1 mic_source PipeWire s16le 2ch 48000Hz RUNNING\\n'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = info ]; then\n'
        "  printf 'Default Source: mic_source\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    pactl.chmod(0o755)

    xdotool = bin_dir / "xdotool"
    xdotool.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    xdotool.chmod(0o755)

    asset_dir = tmp_path / "data"
    asset_dir.mkdir()
    (asset_dir / "voxkeep" / "backends").mkdir(parents=True, exist_ok=True)
    (asset_dir / "voxkeep" / "backends" / "installed.json").write_text(
        "{broken}\n", encoding="utf-8"
    )

    def handler(_ws) -> None:
        return None

    with serve(handler, "127.0.0.1", 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.socket.getsockname()[1]
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["XDG_SESSION_TYPE"] = "x11"
            env["XDG_DATA_HOME"] = str(asset_dir)
            env["VOXKEEP_ASR_BACKEND"] = "funasr_ws_external"
            env["VOXKEEP_ASR_EXTERNAL_HOST"] = "127.0.0.1"
            env["VOXKEEP_ASR_EXTERNAL_PORT"] = str(port)
            env["VOXKEEP_ASR_EXTERNAL_PATH"] = "/"
            env["VOXKEEP_ASR_EXTERNAL_USE_SSL"] = "0"

            proc = subprocess.run(
                ["/bin/bash", str(Path("scripts/check_env.sh"))],
                cwd=Path(__file__).resolve().parents[3],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            server.shutdown()
            thread.join(timeout=1)

    assert proc.returncode != 127
    assert "healthy ok websocket handshake ok" in proc.stdout
