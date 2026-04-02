# Qwen vLLM Real-Service Alignment Handoff

## Goal

Deploy a real local `vLLM/Qwen3-ASR-0.6B` service on this machine, align `QwenVllmEngine` to the real `vLLM/Qwen3-ASR` interface, and complete a reproducible integration check so `VoxKeep` can use `qwen_vllm` against a real external ASR service.

## Repository Context

Repository root:

- `/home/zaviro/workspace/voxkeep-dev`

The project is a local always-on ASR pipeline. It has already been refactored so transcription is no longer hard-wired to FunASR only.

The user wants:

- `Qwen3-ASR-0.6B` as the long-term primary path
- `VoxKeep` to remain only a client of an external ASR service
- no service startup/shutdown responsibility inside `VoxKeep`
- first phase to remain `final-only`
- deployment under user data directories, not under `~/workspace/qwen3-asr`

## Relevant Completed Work

These commits are already in the repository and should be treated as the current baseline:

- `48d98e1` `refactor: add backend-neutral transcription engine seam`
- `6edad8f` `refactor: normalize transcription backend events`
- `fa654e9` `feat: add qwen vllm backend configuration support`
- `7d515ae` `feat: add qwen vllm transcription adapter`
- `52cb5bf` `fix: align transcription engine typing`
- `b4b1a1f` `docs: document qwen vllm as preferred asr path`
- `ceec272` `docs: add qwen asr planning documents`

## Current Code State

The codebase already contains:

- backend-neutral transcription engine seam
- backend-neutral transcription worker/event normalization
- `qwen_vllm` in backend registry and config loading
- a minimal `QwenVllmEngine`
- unit tests for the current adapter/factory path

Important files:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/engine_factory.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/contracts.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_loader.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_schema.py`
- `/home/zaviro/workspace/voxkeep-dev/config/config.yaml`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_transcription_public_api.py`

## Main Gap

`QwenVllmEngine` is currently only a minimal, test-driven adapter. It is not yet validated against the real `vLLM/Qwen3-ASR-0.6B` protocol.

Current risk areas:

- request shape may not match real `vLLM/Qwen3-ASR`
- response parsing may not match real final/partial payloads
- the adapter currently assumes a generic HTTP streaming pattern
- no real service integration has been verified yet

So the next task is not more abstraction. The next task is:

1. deploy the real service
2. inspect the real request/response contract
3. align `QwenVllmEngine`
4. validate integration end-to-end

## Official Sources To Use

Use these official sources first:

- `https://huggingface.co/Qwen/Qwen3-ASR-0.6B`
- `https://docs.vllm.ai/en/stable/api/vllm/model_executor/models/qwen3_asr/`

Useful facts already confirmed from official docs:

- `Qwen3-ASR-0.6B` supports streaming inference
- streaming inference is currently available with the `vLLM` backend
- `qwen-asr-serve` is provided as a wrapper around `vllm serve`
- official examples show OpenAI-compatible interfaces, including:
  - `/v1/chat/completions`
  - OpenAI transcription API support on `vLLM`

## Recommended Real Deployment Layout

Do not deploy under `~/workspace/qwen3-asr`.

Use these paths instead:

- service working dir:
  - `~/.local/share/voxkeep/qwen3-asr-service`
- Hugging Face / model cache:
  - `~/.local/share/voxkeep/huggingface`
- runtime state and logs:
  - `~/.local/state/voxkeep`
- systemd user service:
  - `~/.config/systemd/user/voxkeep-qwen3-asr.service`

Reason:

- this is a runtime dependency, not a source repo you expect to edit often
- it keeps service lifecycle independent from development worktrees
- it matches the current architecture where `VoxKeep` depends on an external service

## Recommended Manual Deployment Steps

Create directories:

```bash
mkdir -p ~/.local/share/voxkeep/qwen3-asr-service
mkdir -p ~/.local/share/voxkeep/huggingface
mkdir -p ~/.local/state/voxkeep
cd ~/.local/share/voxkeep/qwen3-asr-service
```

Create environment:

```bash
uv venv --python 3.11
source .venv/bin/activate
```

Install runtime:

```bash
uv pip install -U vllm --pre \
  --extra-index-url https://wheels.vllm.ai/nightly/cu129 \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --index-strategy unsafe-best-match

uv pip install "vllm[audio]" qwen-asr
```

Start the service manually first:

```bash
export HF_HOME=$HOME/.local/share/voxkeep/huggingface
export CUDA_VISIBLE_DEVICES=0

qwen-asr-serve Qwen/Qwen3-ASR-0.6B \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.8
```

Fallback manual command:

```bash
export HF_HOME=$HOME/.local/share/voxkeep/huggingface
export CUDA_VISIBLE_DEVICES=0

vllm serve Qwen/Qwen3-ASR-0.6B \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.8
```

## Current VoxKeep Config Direction

The intended runtime config shape is:

```yaml
asr:
  backend: qwen_vllm
  mode: external
  external:
    host: 127.0.0.1
    port: 8000
    path: /v1/audio/transcriptions
    use_ssl: false
  runtime:
    reconnect_initial_s: 1.0
    reconnect_max_s: 30.0
```

Important:

- the `path` above is only the current best direction
- the real endpoint path must be confirmed from the actual service
- if the real service needs `/v1/chat/completions`, multipart upload, SSE, or another shape, the adapter and config must be updated accordingly

## Concrete Task List

### 1. Deploy And Start Real Service

- deploy `Qwen3-ASR-0.6B` locally with `qwen-asr-serve` or `vllm serve`
- record exact commands used
- confirm service starts successfully on the target GPU
- record memory usage and any launch flags required

### 2. Probe The Real API

Using `curl` or Python, determine the real request/response contract:

- whether `/v1/audio/transcriptions` works
- whether `/v1/chat/completions` with audio content works
- what streaming mode actually returns
- whether audio must be:
  - file upload
  - URL
  - base64
  - multipart/form-data
  - OpenAI-style SDK payload
- what final and partial payload shapes actually look like
- whether timestamps are available in the serving path being used

Preserve concrete request/response examples during the investigation.

### 3. Align `QwenVllmEngine`

Update:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`

Requirements:

- match the real protocol rather than a guessed one
- keep phase-1 downstream semantics `final-only`
- partial events may be recognized internally, but must not escape public boundaries
- do not silently fall back to another backend or protocol
- log endpoint/protocol failures clearly

### 4. Update Tests

At minimum, add/update tests for:

- real payload parsing based on actual service examples
- non-final event suppression
- endpoint/path selection if config changes
- bad payload / protocol mismatch handling
- any request-builder logic introduced by the real protocol

### 5. Integration Validation

Validate with the real service:

- `qwen_vllm` backend selected in `VoxKeep`
- `VoxKeep` can connect to the real external service
- final transcript is returned through the current public path
- no regression in capture/public/storage final-only behavior

If full microphone runtime validation is not yet practical, at least produce a deterministic local audio request path that proves real service interaction.

### 6. Deployment Handoff

Add:

- `systemd --user` service file
- optional health check command/script
- any config note needed for operators

Suggested service file target:

- `~/.config/systemd/user/voxkeep-qwen3-asr.service`

## Constraints

Must respect repository rules:

- use `uv run --python 3.11 ...`
- do not add runtime logic under `src/voxkeep/core/`, `src/voxkeep/infra/`, or `src/voxkeep/services/`
- do not make `VoxKeep` own Qwen service startup/shutdown
- do not add silent fallback behavior
- if config or behavior changes, update tests and docs

Do not treat environment problems as code bugs unless proven.

## Likely Files To Modify

Primary:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/engine_factory.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_loader.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_schema.py`
- `/home/zaviro/workspace/voxkeep-dev/config/config.yaml`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_transcription_public_api.py`

Secondary if needed:

- `/home/zaviro/workspace/voxkeep-dev/tests/unit/bootstrap/test_runtime_app.py`
- `/home/zaviro/workspace/voxkeep-dev/AGENTS.md`

## Suggested Validation Order

1. `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_backends.py -q`
2. `uv run --python 3.11 python -m pytest tests/unit/shared/test_config.py -q`
3. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_qwen_vllm.py -q`
4. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_transcription_public_api.py -q`
5. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_funasr_ws.py -q`
6. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_asr_worker.py -q`
7. `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py -q`
8. `uv run --python 3.11 python -m pytest tests/architecture -q`
9. `make typecheck`
10. `make test-fast`

Then separately run real service health checks and integration probes.

## Success Criteria

This handoff is complete when:

- real local `Qwen3-ASR-0.6B` service starts successfully
- actual serving API is documented with concrete examples
- `QwenVllmEngine` matches the real interface
- `VoxKeep` with `qwen_vllm` can obtain a real final transcript
- final-only downstream behavior is preserved
- relevant tests and type checks pass
- deployment and operator steps are reproducible
