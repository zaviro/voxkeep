import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_cli_help_end_to_end():
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ROOT / 'src'}{os.pathsep}{old_pythonpath}".strip(os.pathsep)

    proc = subprocess.run(
        [sys.executable, "-m", "asr_ol", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    assert "Local ASR wake capture injector" in proc.stdout
