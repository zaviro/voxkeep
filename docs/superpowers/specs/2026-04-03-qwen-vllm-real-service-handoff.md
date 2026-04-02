# Qwen vLLM Real-Service Alignment Handoff

## Goal

Deploy a real local `Qwen/Qwen3-ASR-0.6B` service on this machine, align `QwenVllmEngine` to the real upstream `vLLM/Qwen3-ASR` protocol, and complete a reproducible integration check so `VoxKeep` can use `qwen_vllm` against a real external ASR service.

This document is an execution handoff, not a brainstorm. It is intentionally opinionated and only keeps steps that match the current repository shape.

## Outcome Required

At the end of this work, all of the following must be true:

- a real local `Qwen3-ASR-0.6B` service can be started outside `VoxKeep`
- `VoxKeep` can connect to it using the `qwen_vllm` backend
- phase-1 downstream behavior remains `final-only`
- no silent fallback to FunASR or a guessed protocol exists
- operator setup is reproducible on this machine

## Repository Context

Repository root:

- `/home/zaviro/workspace/voxkeep-dev`

Primary constraints from the current repository:

- `VoxKeep` must remain a client of an external ASR service
- service lifecycle must stay outside `VoxKeep`
- repository Python stays `3.11` and project commands run through `uv`
- runtime code must stay under `src/voxkeep/modules/*`
- cross-module behavior must keep flowing through module public APIs

## Current Baseline

Already present in the repository:

- backend-neutral transcription engine seam
- backend-neutral transcription worker/event normalization
- `qwen_vllm` in backend registry and config loading
- a minimal `QwenVllmEngine`
- unit tests for the current adapter/factory path

Relevant files:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/engine_factory.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/contracts.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/asr_backends.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_loader.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_schema.py`
- `/home/zaviro/workspace/voxkeep-dev/config/config.yaml`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_transcription_public_api.py`

## Main Correction To The Previous Draft

The previous draft was directionally correct but not executable as written.

The important correction is:

- do not treat `Qwen3-ASR` as a generic per-frame HTTP JSON endpoint
- do not assume the current `audio: <base64>` POST body is valid
- do not start implementation from `/v1/audio/transcriptions` as the primary transport for continuous runtime streaming

Why:

- the current repository feeds `ProcessedFrame` objects continuously into the transcription engine
- the current `QwenVllmEngine` submits one request per frame
- for this runtime shape, the real `vLLM` realtime WebSocket path is the best protocol match
- file-style transcription endpoints may still be useful for probing and deterministic integration tests, but they are not the primary runtime transport for the current architecture

## Source Of Truth

Use official upstream docs first and prefer concrete observed behavior over assumptions.

Primary sources:

- `https://huggingface.co/Qwen/Qwen3-ASR-0.6B`
- `https://docs.vllm.ai/en/stable/serving/openai_compatible_server.html`
- `https://docs.vllm.ai/en/stable/features/realtime.html`
- `https://docs.vllm.ai/en/stable/api/vllm/entrypoints/openai/speech_to_text/protocol/`

When the actual running service behavior differs from this document, update this document and the adapter to match the observed upstream protocol rather than preserving the previous local guess.

## Recommended Deployment Layout

Do not deploy under `~/workspace/qwen3-asr`.

Use these paths instead:

- service working dir:
  - `~/.local/share/voxkeep/qwen3-asr-service`
- Hugging Face cache:
  - `~/.local/share/voxkeep/huggingface`
- runtime state and logs:
  - `~/.local/state/voxkeep`
- user service unit:
  - `~/.config/systemd/user/voxkeep-qwen3-asr.service`

Reason:

- this keeps the model service independent from source worktrees
- it matches the current architecture where `VoxKeep` depends on an externally managed service
- it avoids mixing runtime assets with repository state

## Environment Notes For This Machine

As validated during handoff preparation on `2026-04-03`:

- GPU: `NVIDIA GeForce RTX 5060 Ti`
- VRAM: `16311 MiB`
- driver: `580.126.09`
- `uv`: available
- project Python: `3.11.14`

Practical guidance:

- keep `VoxKeep` itself on Python `3.11`
- allow the external Qwen service environment to use the Python version required by the upstream package if needed
- if `qwen-asr` or `vllm` packaging is stricter than the repository runtime, treat the service venv as independent from the project venv

## Runtime Protocol Decision

### Primary Runtime Transport

Use `vLLM` realtime WebSocket as the primary runtime protocol.

Target behavior:

- open one long-lived WebSocket session from `QwenVllmEngine`
- send audio incrementally as frames arrive
- commit/flush according to runtime sentence boundaries or backend requirements
- consume realtime transcript events
- suppress partial/delta events before they cross module public boundaries
- emit only final transcript events into the current downstream path

### Secondary Probe Path

Also verify whether `/v1/audio/transcriptions` works on the local service.

Use it only for:

- deterministic health checks
- protocol inspection
- fixture-based integration verification

Do not build the main runtime engine around file upload first unless realtime serving is unavailable or proven unstable on the actual service version being deployed.

## Current Code Gaps

`QwenVllmEngine` is currently a minimal adapter and must not be treated as protocol-correct.

Current risk areas:

- request body shape is guessed
- response parsing is guessed
- current implementation posts one HTTP request per frame
- current implementation assumes generic JSON or SSE-like line responses
- no real-service contract has been validated yet

Therefore the next task is not more abstraction. The next task is:

1. deploy the real service
2. inspect the real request/response contract
3. align `QwenVllmEngine` to that contract
4. validate end-to-end behavior

## Intended VoxKeep Config Direction

The intended runtime config direction remains:

```yaml
asr:
  backend: qwen_vllm
  mode: external
  external:
    host: 127.0.0.1
    port: 8000
    path: /v1/realtime
    use_ssl: false
  runtime:
    reconnect_initial_s: 1.0
    reconnect_max_s: 30.0
```

Important:

- the path above is now intentionally `realtime`-oriented
- if the deployed upstream version requires a different realtime endpoint shape, update config and adapter together
- do not silently reinterpret a realtime path as file transcription

For deterministic probe scripts or fixture checks, a separate explicit path may be used:

- `/v1/audio/transcriptions`

But that should not replace the primary runtime transport decision unless realtime is rejected by verified service behavior.

## Concrete Task List

### 1. Deploy And Start The Real Service

Create directories:

```bash
mkdir -p ~/.local/share/voxkeep/qwen3-asr-service
mkdir -p ~/.local/share/voxkeep/huggingface
mkdir -p ~/.local/state/voxkeep
cd ~/.local/share/voxkeep/qwen3-asr-service
```

Create a dedicated service environment.

Preferred first attempt:

```bash
uv venv --python 3.11
source .venv/bin/activate
```

If upstream package constraints reject Python `3.11`, create the service venv with the Python version accepted by the upstream package. This does not require changing the repository runtime version.

Install runtime packages using the upstream-recommended path for the service version you actually deploy.

Start manually before writing the systemd unit:

```bash
export HF_HOME=$HOME/.local/share/voxkeep/huggingface
export CUDA_VISIBLE_DEVICES=0

qwen-asr-serve Qwen/Qwen3-ASR-0.6B \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.8
```

Fallback if the wrapper is unavailable:

```bash
export HF_HOME=$HOME/.local/share/voxkeep/huggingface
export CUDA_VISIBLE_DEVICES=0

vllm serve Qwen/Qwen3-ASR-0.6B \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.8
```

Record:

- exact command used
- exact installed package versions
- whether the wrapper or raw `vllm serve` was used
- GPU memory usage after load
- any additional launch flags required

### 2. Probe The Real API

Using `curl`, `websocat`, or a short Python script, determine the actual contract used by the running service.

Probe all of the following:

- whether `/health` or a similar readiness endpoint exists
- whether `/v1/models` responds
- whether `/v1/audio/transcriptions` responds
- whether `/v1/realtime` responds
- what authentication, if any, is required in local mode
- whether realtime audio chunks are base64, binary, or another envelope
- what the actual event names are for partial and final transcript output
- whether timestamps are present in the realtime result path

Preserve concrete request/response examples captured from the running service.

Minimum required artifacts from this probe:

- one successful realtime connection example
- one successful final transcript example
- one example of a non-final transcript event if upstream emits it
- one file transcription example if `/v1/audio/transcriptions` is supported

### 3. Align `QwenVllmEngine`

Modify:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/asr_backends.py`

Possibly modify if required by the final protocol choice:

- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_schema.py`
- `/home/zaviro/workspace/voxkeep-dev/src/voxkeep/shared/config_loader.py`
- `/home/zaviro/workspace/voxkeep-dev/config/config.yaml`

Requirements:

- match the real protocol rather than a guessed one
- prefer one long-lived realtime connection over one HTTP request per frame
- keep downstream public semantics `final-only`
- partial events may be consumed internally but must not escape public boundaries
- log protocol failures clearly with endpoint details
- do not silently fall back to another backend, transport, or path

If realtime requires a session-level handshake, encapsulate it inside `QwenVllmEngine`.

If sentence finalization requires an explicit commit boundary, the implementation must make that boundary explicit and testable. Do not bury it in undocumented timing heuristics.

### 4. Update Tests

At minimum, add or update tests for:

- realtime event parsing based on real captured payload examples
- suppression of non-final or delta events
- request/session setup for the chosen realtime protocol
- reconnect and protocol mismatch handling
- endpoint/path selection if config changes
- file-transcription probe parsing if that path is kept for deterministic validation

Relevant tests:

- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_qwen_vllm.py`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_transcription_public_api.py`
- `/home/zaviro/workspace/voxkeep-dev/tests/unit/modules/transcription/test_asr_worker.py`

If the adapter introduces more complex session state, split that logic into testable helpers instead of hiding everything inside one thread loop.

### 5. Integration Validation

Validate in this order:

1. external service starts and responds
2. deterministic probe audio can obtain a final transcript from the real service
3. `VoxKeep` with `qwen_vllm` selected can connect to the external service
4. final transcript reaches the current public path
5. no regression in `capture`, `storage`, and final-only behavior

If full microphone runtime validation is not yet practical, a deterministic local audio request path is acceptable for the service-level validation, but the repository still needs at least one integration check proving the `qwen_vllm` engine can talk to the real service.

### 6. Deployment Handoff

Add:

- a `systemd --user` service file
- an optional health-check command or script
- operator notes for enabling the backend in `config/config.yaml`

Suggested service file target:

- `~/.config/systemd/user/voxkeep-qwen3-asr.service`

## What Not To Do

- do not leave the current guessed JSON-per-frame adapter in place and only change docs
- do not claim realtime support without capturing actual event examples from the running service
- do not silently convert `qwen_vllm` selection into FunASR behavior
- do not put service startup/shutdown inside `VoxKeep`
- do not deep-import around module boundaries for convenience
- do not claim success based only on unit tests without a real-service probe

## Suggested Validation Commands

Run the narrowest commands that prove the actual change.

Repository validation:

1. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_qwen_vllm.py -q`
2. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_transcription_public_api.py -q`
3. `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_asr_worker.py -q`
4. `uv run --python 3.11 python -m pytest tests/architecture -q`
5. `make validate-config`

If config defaults or docs are updated for operator flow:

6. `make cli-check`

Service-side validation should also be recorded separately, for example:

1. `curl http://127.0.0.1:8000/v1/models`
2. realtime probe script against `ws://127.0.0.1:8000/v1/realtime`
3. optional file transcription probe against `http://127.0.0.1:8000/v1/audio/transcriptions`

## Acceptance Criteria

This handoff is complete only when all of the following are true:

- the real local `Qwen3-ASR-0.6B` service starts successfully on this machine
- the chosen service protocol is confirmed from real request/response evidence
- `QwenVllmEngine` is aligned to that real protocol
- `VoxKeep` with `qwen_vllm` can obtain a real final transcript from the external service
- partial transcript behavior does not leak past the transcription module public boundary
- operator instructions are sufficient to reproduce the setup without hidden local assumptions

## Deliverables

Required deliverables from the implementation pass:

- updated `QwenVllmEngine`
- updated tests based on real observed payloads
- any required config updates
- systemd user service file text
- health-check or probe instructions
- exact service launch command and package versions used
- a short implementation note recording the verified protocol and why it was chosen
