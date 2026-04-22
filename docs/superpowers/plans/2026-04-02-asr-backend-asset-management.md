# ASR Backend And Asset Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the non-reproducible FunASR coupling with a FunASR-first backend registry, hybrid backend resolution, stronger health checks, and explicit backend management commands.

**Architecture:** Keep the first version narrow and FunASR-only. Add backend-oriented config and registry metadata in `shared/`, expose backend inspection and doctor commands in the CLI, teach runtime/transcription to resolve endpoint settings from backend selection, and replace the unmanaged `gpudokerasr` default with an explicit official image reference plus compatibility handling for existing `funasr.*` config.

**Tech Stack:** Python 3.11, `uv`, argparse CLI, dataclass config schema, existing FunASR WebSocket runtime, pytest unit/integration tests, shell-based environment checks.

---

## File Structure

Planned file responsibilities for the first implementation slice:

- Modify: `src/voxkeep/shared/config_schema.py`
  - Extend immutable config with ASR backend mode, backend id, managed image/source metadata, and compatibility helpers.
- Modify: `src/voxkeep/shared/config_defaults.py`
  - Define reproducible default ASR backend settings and remove the local-only `gpudokerasr` default.
- Modify: `src/voxkeep/shared/config_env.py`
  - Add environment variable overrides for new ASR settings.
- Modify: `src/voxkeep/shared/config_loader.py`
  - Load new `asr.*` config, map legacy `funasr.*` fields into the new model, and validate compatibility.
- Create: `src/voxkeep/shared/asr_backends.py`
  - Define backend registry metadata, backend status enums, and backend resolution helpers for FunASR-first behavior.
- Create: `src/voxkeep/shared/asr_assets.py`
  - Define installed-assets state file location and read/write helpers under user data directories.
- Create: `src/voxkeep/shared/asr_health.py`
  - Implement FunASR TCP + WebSocket readiness checks and normalized status reporting.
- Modify: `src/voxkeep/modules/transcription/infrastructure/funasr_ws.py`
  - Resolve WebSocket endpoint through the new backend config rather than legacy direct fields.
- Modify: `src/voxkeep/cli/main.py`
  - Add `backend` and `asset` command groups for list/current/use/doctor/status operations.
- Modify: `scripts/check_env.sh`
  - Reuse stronger backend doctor checks instead of raw TCP-only probing.
- Modify: `scripts/run_local.sh`
  - Replace implicit local-only image assumptions with explicit backend-aware managed startup defaults.
- Modify: `docker-compose.yml`
  - Replace `gpudokerasr` with an official FunASR image reference or explicit environment variable contract.
- Modify: `README.md`
  - Document backend modes, managed versus external behavior, and cleanup/deployment guidance.
- Test: `tests/unit/shared/test_config.py`
  - Cover config compatibility and new backend fields.
- Test: `tests/unit/cli/test_main.py`
  - Cover new backend and asset CLI commands.
- Test: `tests/unit/modules/transcription/test_funasr_ws.py`
  - Cover resolved endpoint behavior.
- Create: `tests/unit/shared/test_asr_backends.py`
  - Cover backend registry and resolution logic.
- Create: `tests/unit/shared/test_asr_health.py`
  - Cover health state mapping and failure classification.
- Create: `tests/unit/shared/test_asr_assets.py`
  - Cover state file path and persistence behavior.

### Task 1: Add Backend Registry And Config Compatibility

**Files:**
- Create: `src/voxkeep/shared/asr_backends.py`
- Modify: `src/voxkeep/shared/config_schema.py`
- Modify: `src/voxkeep/shared/config_defaults.py`
- Modify: `src/voxkeep/shared/config_env.py`
- Modify: `src/voxkeep/shared/config_loader.py`
- Test: `tests/unit/shared/test_asr_backends.py`
- Test: `tests/unit/shared/test_config.py`

- [ ] **Step 1: Write the failing backend registry test**

```python
from voxkeep.shared.asr_backends import BUILTIN_BACKENDS, resolve_backend_definition


def test_builtin_registry_contains_funasr_external_and_managed() -> None:
    assert "funasr_ws_external" in BUILTIN_BACKENDS
    assert "funasr_ws_managed" in BUILTIN_BACKENDS
    assert resolve_backend_definition("funasr_ws_external").transport == "websocket"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_backends.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors because `asr_backends.py` does not exist yet.

- [ ] **Step 3: Write the failing config compatibility test**

```python
from voxkeep.shared.config import load_config


def test_load_config_maps_legacy_funasr_fields_to_asr_backend(tmp_path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "funasr:\\n"
        "  host: 127.0.0.1\\n"
        "  port: 10096\\n"
        "  path: /\\n"
        "  use_ssl: false\\n"
        "  reconnect_initial_s: 1.0\\n"
        "  reconnect_max_s: 30.0\\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr_backend == "funasr_ws_external"
    assert cfg.asr_mode == "auto"
    assert cfg.asr_external_host == "127.0.0.1"
```

- [ ] **Step 4: Run targeted config test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_config.py -q`
Expected: FAIL because `AppConfig` and loader do not yet expose `asr_backend`, `asr_mode`, or `asr_external_host`.

- [ ] **Step 5: Implement backend registry and config schema changes**

```python
@dataclass(slots=True, frozen=True)
class AsrBackendDefinition:
    backend_id: str
    display_name: str
    kind: str
    transport: str
    managed_by_default: bool


BUILTIN_BACKENDS = {
    "funasr_ws_external": AsrBackendDefinition(...),
    "funasr_ws_managed": AsrBackendDefinition(...),
}


def resolve_backend_definition(backend_id: str) -> AsrBackendDefinition:
    try:
        return BUILTIN_BACKENDS[backend_id]
    except KeyError as exc:
        raise ValueError(f"unsupported asr backend: {backend_id}") from exc
```

```python
@dataclass(slots=True, frozen=True)
class AppConfig:
    ...
    asr_backend: str
    asr_mode: str
    asr_external_host: str
    asr_external_port: int
    asr_external_path: str
    asr_external_use_ssl: bool
    asr_managed_provider: str
    asr_managed_image: str
    asr_managed_service_name: str
    asr_managed_expose_port: int
```

```python
DEFAULTS["asr"] = {
    "backend": "funasr_ws_external",
    "mode": "auto",
    "external": {
        "host": "127.0.0.1",
        "port": 10096,
        "path": "/",
        "use_ssl": False,
    },
    "managed": {
        "provider": "docker",
        "image": "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13",
        "service_name": "funasr",
        "expose_port": 10096,
    },
}
```

```python
def _merge_legacy_funasr(conf: dict[str, Any]) -> dict[str, Any]:
    legacy = conf.get("funasr")
    if not isinstance(legacy, dict):
        return conf
    _set_nested(conf, "asr.external.host", legacy.get("host", "127.0.0.1"))
    _set_nested(conf, "asr.external.port", legacy.get("port", 10096))
    _set_nested(conf, "asr.external.path", legacy.get("path", "/"))
    _set_nested(conf, "asr.external.use_ssl", legacy.get("use_ssl", False))
    return conf
```

- [ ] **Step 6: Run the new shared tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_backends.py tests/unit/shared/test_config.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/voxkeep/shared/asr_backends.py src/voxkeep/shared/config_schema.py src/voxkeep/shared/config_defaults.py src/voxkeep/shared/config_env.py src/voxkeep/shared/config_loader.py tests/unit/shared/test_asr_backends.py tests/unit/shared/test_config.py
git commit -m "feat: add asr backend config and registry"
```

### Task 2: Add Backend Health Checks And Installed Asset State

**Files:**
- Create: `src/voxkeep/shared/asr_health.py`
- Create: `src/voxkeep/shared/asr_assets.py`
- Create: `tests/unit/shared/test_asr_health.py`
- Create: `tests/unit/shared/test_asr_assets.py`
- Modify: `scripts/check_env.sh`

- [ ] **Step 1: Write the failing health classification test**

```python
from voxkeep.shared.asr_health import AsrHealthStatus, classify_health_result


def test_classify_health_result_prefers_protocol_error_over_tcp_only_success() -> None:
    status = classify_health_result(tcp_ok=True, handshake_ok=False, detail="bad handshake")
    assert status.state == "degraded"
    assert status.reason == "handshake_failed"
```

- [ ] **Step 2: Run health test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_health.py -q`
Expected: FAIL because `asr_health.py` does not exist yet.

- [ ] **Step 3: Write the failing assets state test**

```python
from voxkeep.shared.asr_assets import assets_state_path, write_assets_state, read_assets_state


def test_assets_state_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    write_assets_state({"funasr_ws_managed": {"installed": True}})
    assert read_assets_state()["funasr_ws_managed"]["installed"] is True
    assert assets_state_path().name == "installed.json"
```

- [ ] **Step 4: Run assets test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_assets.py -q`
Expected: FAIL because `asr_assets.py` does not exist yet.

- [ ] **Step 5: Implement health and assets helpers**

```python
@dataclass(slots=True, frozen=True)
class AsrHealthStatus:
    state: str
    reason: str
    detail: str


def classify_health_result(*, tcp_ok: bool, handshake_ok: bool, detail: str) -> AsrHealthStatus:
    if not tcp_ok:
        return AsrHealthStatus("unavailable", "tcp_unreachable", detail)
    if not handshake_ok:
        return AsrHealthStatus("degraded", "handshake_failed", detail)
    return AsrHealthStatus("healthy", "ok", detail)
```

```python
def assets_state_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "voxkeep" / "backends" / "installed.json"


def write_assets_state(data: dict[str, Any]) -> None:
    path = assets_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
```

- [ ] **Step 6: Strengthen doctor script to use backend-aware checks**

```bash
echo "== FunASR backend health =="
if run_python -m voxkeep backend doctor; then
  mark_pass "FunASR backend health"
else
  mark_fail "FunASR backend health"
fi
```

- [ ] **Step 7: Run shared tests and doctor-related CLI test subset**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_health.py tests/unit/shared/test_asr_assets.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/voxkeep/shared/asr_health.py src/voxkeep/shared/asr_assets.py scripts/check_env.sh tests/unit/shared/test_asr_health.py tests/unit/shared/test_asr_assets.py
git commit -m "feat: add asr health and asset state helpers"
```

### Task 3: Add Backend And Asset CLI Commands

**Files:**
- Modify: `src/voxkeep/cli/main.py`
- Modify: `src/voxkeep/shared/config.py` if export surface needs update
- Test: `tests/unit/cli/test_main.py`

- [ ] **Step 1: Write the failing backend list CLI test**

```python
from voxkeep.cli.main import main


def test_backend_list_command_prints_known_backends(capsys) -> None:
    exit_code = main(["backend", "list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "funasr_ws_external" in captured.out
    assert "funasr_ws_managed" in captured.out
```

- [ ] **Step 2: Run the CLI test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/cli/test_main.py -q`
Expected: FAIL because `backend` subcommands do not exist.

- [ ] **Step 3: Add failing backend doctor CLI test**

```python
def test_backend_doctor_returns_failure_for_unreachable_service(monkeypatch, capsys) -> None:
    monkeypatch.setattr("voxkeep.cli.main.run_backend_doctor", lambda *_args, **_kwargs: 1)
    exit_code = main(["backend", "doctor"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "backend doctor failed" in captured.err
```

- [ ] **Step 4: Implement backend and asset command groups**

```python
def _cmd_backend_list(_args: argparse.Namespace) -> int:
    for backend in BUILTIN_BACKENDS.values():
        print(f"{backend.backend_id}\t{backend.kind}\t{backend.transport}")
    return EXIT_OK


def _cmd_backend_current(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(cfg.asr_backend)
    return EXIT_OK
```

```python
backend_parser = subparsers.add_parser("backend", help="ASR backend helpers")
backend_subparsers = backend_parser.add_subparsers(dest="backend_command", required=True)
backend_subparsers.add_parser("list", help="List built-in backends").set_defaults(func=_cmd_backend_list)
```

- [ ] **Step 5: Run CLI tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/cli/test_main.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/voxkeep/cli/main.py tests/unit/cli/test_main.py
git commit -m "feat: add backend and asset cli commands"
```

### Task 4: Route FunASR Endpoint Through Backend Resolution

**Files:**
- Modify: `src/voxkeep/modules/transcription/infrastructure/funasr_ws.py`
- Modify: `src/voxkeep/modules/transcription/public.py`
- Test: `tests/unit/modules/transcription/test_funasr_ws.py`

- [ ] **Step 1: Write the failing endpoint resolution test**

```python
from dataclasses import replace

from voxkeep.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine


def test_engine_uses_backend_resolved_external_url(app_config, monkeypatch) -> None:
    cfg = replace(app_config, asr_external_host="10.0.0.8", asr_external_port=3210, asr_external_path="/ws")
    engine = FunAsrWsEngine(cfg=cfg, stop_event=threading.Event())
    assert engine._cfg.asr_ws_url == "ws://10.0.0.8:3210/ws"
```

- [ ] **Step 2: Run transcription test to verify failure**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_funasr_ws.py -q`
Expected: FAIL because config compatibility and URL properties still point to legacy-only fields.

- [ ] **Step 3: Implement backend-resolved URL properties**

```python
@property
def asr_ws_url(self) -> str:
    scheme = "wss" if self.asr_external_use_ssl else "ws"
    return f"{scheme}://{self.asr_external_host}:{self.asr_external_port}{self.asr_external_path}"
```

```python
resolved_backend = resolve_backend_definition(cfg.asr_backend)
if resolved_backend.transport != "websocket":
    raise ValueError(f"unsupported transport for FunAsrWsEngine: {resolved_backend.transport}")
```

- [ ] **Step 4: Run focused transcription tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_funasr_ws.py tests/unit/modules/transcription/test_transcription_public_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/voxkeep/modules/transcription/infrastructure/funasr_ws.py src/voxkeep/modules/transcription/public.py tests/unit/modules/transcription/test_funasr_ws.py
git commit -m "refactor: resolve funasr endpoint through backend config"
```

### Task 5: Replace Unreproducible Managed Defaults And Update Runtime Scripts

**Files:**
- Modify: `scripts/run_local.sh`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Test: `tests/unit/cli/test_main.py` if run docs examples are asserted

- [ ] **Step 1: Write the failing script expectation test or shell assertion**

```bash
rg -n "gpudokerasr" scripts/run_local.sh docker-compose.yml README.md
```

Expected: current matches found.

- [ ] **Step 2: Replace managed image contract with an explicit official image reference**

```bash
FUNASR_IMAGE="${VOXKEEP_FUNASR_IMAGE:-registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13}"
```

```yaml
services:
  funasr:
    image: ${VOXKEEP_FUNASR_IMAGE:-registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13}
```

- [ ] **Step 3: Update run script logging and failure messaging**

```bash
echo "ASR backend mode=${VOXKEEP_ASR_MODE:-auto} managed_image=${FUNASR_IMAGE}"
echo "Hint: set VOXKEEP_MANAGE_FUNASR=0 to use an external already-running FunASR service."
```

- [ ] **Step 4: Update README deployment and cleanup guidance**

```markdown
- default managed FunASR image now uses an explicit official image reference
- `VOXKEEP_MANAGE_FUNASR=0` selects external service mode
- keep source-backed FunASR only as an optional fallback, not as the default deployment path
```

- [ ] **Step 5: Verify removal of unreproducible defaults**

Run: `rg -n "gpudokerasr|/home/user/workspace/FunASR" README.md docker-compose.yml scripts/run_local.sh src config`
Expected: no matches in active runtime paths or user-facing docs.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_local.sh docker-compose.yml README.md
git commit -m "fix: replace non-reproducible funasr defaults"
```

### Task 6: Verify The First Slice End To End

**Files:**
- Modify: `docs/superpowers/specs/2026-04-02-asr-backend-asset-management-design.md` only if discovered behavior requires clarification
- No planned code files beyond fixes needed from verification

- [ ] **Step 1: Run formatting and linting**

Run: `make fmt && make lint`
Expected: PASS

- [ ] **Step 2: Run type checking**

Run: `make typecheck`
Expected: PASS, or explicit note if runtime-ai packages are intentionally missing.

- [ ] **Step 3: Run fast tests including new shared and CLI coverage**

Run: `make test-fast`
Expected: PASS

- [ ] **Step 4: Run focused integration or CLI checks for backend doctor path**

Run: `make cli-check`
Expected: PASS

- [ ] **Step 5: Run environment doctor against the updated backend-aware checks**

Run: `make doctor`
Expected: either PASS with a healthy external or managed FunASR service, or FAIL with a precise backend-specific explanation rather than a raw TCP refusal.

- [ ] **Step 6: Commit any verification-driven doc or message fixes**

```bash
git add README.md scripts/check_env.sh src tests
git commit -m "test: verify asr backend management first slice"
```

## Self-Review

Spec coverage check:

- backend-oriented config is covered by Task 1
- registry metadata is covered by Task 1
- health checks are covered by Task 2
- installed assets state file is covered by Task 2
- CLI surface is covered by Task 3
- runtime/transcription endpoint resolution is covered by Task 4
- deployment and cleanup guidance is covered by Task 5
- verification is covered by Task 6

Placeholder scan:

- no `TBD`, `TODO`, or unresolved placeholder steps remain

Type consistency:

- `asr_backend`, `asr_mode`, and `asr_external_*` names are used consistently across config, CLI, and runtime tasks
