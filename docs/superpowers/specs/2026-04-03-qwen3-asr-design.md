# VoxKeep Qwen3-ASR-0.6B Integration Design

## Context

VoxKeep currently treats ASR as a FunASR-specific WebSocket session embedded inside the transcription module.

The current implementation is tightly coupled to FunASR-specific protocol details:

- `transcription/public.py` directly instantiates `FunAsrWsEngine`
- the engine sends FunASR-only control payloads such as `mode=2pass`
- the engine assumes a continuous PCM16 frame stream over one long-lived socket
- only final transcript events are surfaced to the rest of the runtime

This shape is enough for the existing FunASR path, but it is not a stable long-term interface for backend selection. It makes protocol replacement more expensive than it should be and prevents VoxKeep from taking advantage of clearer upstream serving models.

The target backend for the first long-term production path is `Qwen3-ASR-0.6B`, served as an independent local `vLLM` service. VoxKeep should act only as a client of that service.

## Goals

- Adopt `Qwen3-ASR-0.6B` as the first long-term production ASR backend
- Keep ASR service ownership outside VoxKeep:
  - VoxKeep connects to an already-running local service
  - VoxKeep does not start, stop, or supervise `vLLM`
- Refactor the transcription module so backend protocol details stay inside backend adapters
- Preserve the current public runtime behavior for phase 1:
  - final transcript only
  - no capture semantics change
  - no wake/action semantics change
- Make the backend path maintainable enough to add a second backend later without reworking module boundaries

## Non-Goals

- Do not make phase 1 consume partial transcript events in `capture`
- Do not preserve the FunASR private WebSocket protocol as a future compatibility target
- Do not build a general ASR gateway service in this phase
- Do not make VoxKeep responsible for `vLLM` deployment orchestration
- Do not redesign wake, VAD, injection, or storage behavior

## Decision Summary

The first production integration should use:

- backend: `Qwen3-ASR-0.6B`
- deployment shape: independent local `vLLM` service
- VoxKeep role: ASR streaming client only
- runtime transcript semantics for phase 1: `final-only`
- integration style: backend abstraction inside `modules/transcription`, with a dedicated Qwen `vLLM` adapter

This means the migration is not just a backend URL swap. The important change is moving from a FunASR-bound transport implementation to a backend-oriented transcription module.

## Why This Direction

### Why `Qwen3-ASR-0.6B`

For this project, `Qwen3-ASR-0.6B` is the better first long-term path than `FireRedASR v2` because it is more balanced operationally:

- realistic for a single local GPU desktop deployment
- official streaming support is explicitly documented
- official serving/tooling story is clearer
- bilingual and multilingual coverage is strong enough for the product target
- easier to standardize as a long-running local service

### Why Independent Service Ownership

Keeping `vLLM` outside VoxKeep makes the system easier to reason about:

- VoxKeep remains an application runtime, not a service supervisor
- deployment and operations concerns stay separate from the threaded runtime
- backend replacement later is easier because `transcription` stays a protocol consumer
- failures become easier to classify:
  - service unavailable
  - protocol mismatch
  - runtime processing failure

### Why Final-Only First

Phase 1 should keep the current `final transcript` contract because it reduces migration risk:

- `capture` already consumes final transcript events
- storage already supports final-only policy
- wake/action behavior stays stable
- testing scope remains bounded

Partial transcript support is still worth designing for internally, but not yet worth exposing across module boundaries.

## Current Constraints In The Codebase

The current repository architecture imposes clear constraints that the design must respect:

- runtime modules must collaborate through `public.py`
- `capture` currently accepts only `TranscriptFinalized`
- new runtime logic must stay under `src/voxkeep/modules/...`
- `shared/` must not become a backdoor dependency hub into runtime modules

This means the new design should avoid deep imports, avoid protocol details leaking into `capture`, and avoid backend-specific logic in bootstrap wiring.

## Architecture

### 1. Public Runtime Shape

The public contract of `modules/transcription` remains stable for phase 1:

- input: audio frames submitted via `submit_audio`
- output: final transcript events via `subscribe_transcript_finalized`

`capture` continues to receive only finalized transcript events and remains unaware of:

- Qwen
- `vLLM`
- backend-specific streaming payload shapes
- partial transcript traffic

### 2. Internal Transcription Layering

Refactor the transcription module into three internal concerns:

1. `contracts`
   - backend-neutral transcription engine contract
   - backend-neutral transcript message model for the module internals
2. `infrastructure`
   - backend-specific protocol adapters
   - first implementation: Qwen `vLLM` streaming adapter
3. `public.py`
   - configuration-driven backend selection
   - module assembly
   - conversion from internal backend events to public `TranscriptFinalized`

This allows the public module surface to stay stable while backend protocol handling becomes replaceable.

### 3. Backend Contract

The current shared `ASREngine` abstraction is too narrow because it models only lifecycle plus frame submission.

The internal transcription backend contract should instead define:

- start lifecycle
- close lifecycle
- submit processed audio frames
- expose a queue or callback stream of backend transcript events

The internal event model should support both:

- `partial`
- `final`

Even though phase 1 publishes only `final`, the internal contract should not hardcode final-only semantics. Otherwise the next streaming iteration will require another contract rewrite.

### 4. Qwen `vLLM` Adapter

Add a dedicated adapter under `modules/transcription/infrastructure/` for `Qwen3-ASR-0.6B` served by `vLLM`.

Responsibilities:

- connect to the external local `vLLM` streaming endpoint
- transform `ProcessedFrame` input into the request shape expected by the backend
- read streaming responses from the backend
- normalize responses into internal transcript events
- surface only final transcript events to the existing public module flow in phase 1
- log backend connection, reconnection, and protocol failures clearly

The adapter should not:

- start `vLLM`
- download models
- infer deployment ownership
- change capture behavior

### 5. Builder-Based Backend Selection

`modules/transcription/public.py` should no longer directly instantiate `FunAsrWsEngine`.

Instead it should:

- resolve the configured backend
- construct the backend through an internal builder function
- wire the engine into the existing worker/module lifecycle

This gives VoxKeep one place to choose:

- `qwen_vllm`
- legacy `funasr_ws_external` during migration

### 6. Phase 1 Transcript Semantics

Phase 1 keeps the outward transcript semantics unchanged:

- only final transcript events are published to subscribers
- `capture` continues to operate on finalized transcript units
- storage still follows `store_final_only` policy

If Qwen returns partial events, the adapter should:

- discard them
- emit low-volume debug logs when debug logging is enabled

But partials do not cross the module boundary in phase 1.

## Configuration Model

The current config is still FunASR-shaped in naming. Phase 1 should move toward a backend-oriented config model, but without a disruptive full rewrite.

Recommended direction:

- `asr_backend`
  - `qwen_vllm`
  - `funasr_ws_external` during migration
- external service connection settings
  - host/base URL
  - port
  - path or endpoint
  - TLS flag if needed
  - request timeout
  - reconnect policy
- backend-specific settings grouped under backend-specific config sections when necessary

Phase 1 should explicitly avoid carrying forward FunASR-only protocol fields into the generic config surface, such as:

- `mode=2pass`
- `chunk_size`
- `encoder_chunk_look_back`
- `decoder_chunk_look_back`

Compatibility guidance:

- existing FunASR config can remain temporarily for migration
- runtime logs must clearly print the selected backend
- there must be no silent fallback from `qwen_vllm` to FunASR

If the configured backend is unavailable or invalid, VoxKeep should fail loudly with a clear reason.

## Failure Model

The runtime must distinguish backend failures from application logic failures.

Important failure classes:

- external service not reachable
- protocol handshake or schema mismatch
- service accepts connection but does not produce valid transcript events
- queue saturation causing dropped frames or dropped final transcript events
- backend disconnect during active streaming

Required behavior:

- clear structured logs for connection attempts and failures
- reconnect according to configured retry policy
- no silent backend switching
- no silent degradation to a different transport or model

## Deployment Model

Phase 1 deployment model is explicit:

- `Qwen3-ASR-0.6B` runs as an independently managed local `vLLM` service
- deployment ownership belongs to system scripts, container tooling, or service manager configuration outside VoxKeep
- VoxKeep assumes the endpoint exists and is healthy enough to connect

This keeps VoxKeep out of service orchestration while still allowing future packaging work around:

- `systemd`
- Docker Compose
- local helper scripts

Those are deployment concerns, not runtime module concerns.

## Migration Plan

### Phase 1: Internal Backend Abstraction

- add a backend-neutral transcription engine contract inside the transcription module
- make `public.py` depend on a builder instead of directly importing `FunAsrWsEngine`
- preserve the existing public module API

### Phase 2: Qwen Adapter

- implement the `Qwen3-ASR-0.6B` `vLLM` adapter
- normalize backend responses to internal transcript events
- forward final transcript events through the current public flow

### Phase 3: Config And Runtime Selection

- add backend selection for `qwen_vllm`
- preserve legacy FunASR path temporarily for fallback during migration
- update runtime logs and validation so backend choice is explicit

### Phase 4: Validation And Default Recommendation

- validate on the target machine and service layout
- compare end-to-end behavior against current pipeline expectations
- move documentation and operator guidance to the Qwen-first path

## Testing Strategy

### Unit Tests

Add or update tests for:

- backend builder selection by config
- Qwen adapter response parsing
- final-only publication policy
- invalid payload handling
- reconnect and connection-failure logging behavior

### Integration Tests

Add or update tests for:

- `transcription -> capture` final-only event flow
- thread lifecycle under backend disconnect/reconnect conditions
- queue saturation behavior remaining explicit and observable

### Environment Validation

On the target workstation, validate:

- independent `vLLM` service startup outside VoxKeep
- connection success from VoxKeep to the configured endpoint
- stable Chinese transcription
- stable English transcription
- stable mixed Chinese/English transcription
- acceptable end-to-end latency
- acceptable GPU memory usage for long-running desktop residency

Environment failures must be reported as environment issues unless a code defect is proven.

## Acceptance Criteria

The design is successful for phase 1 when all of the following are true:

- VoxKeep can use `Qwen3-ASR-0.6B` through an externally managed `vLLM` service
- `capture` remains final-only and behaviorally unchanged
- `transcription/public.py` no longer hardcodes a FunASR engine implementation
- backend selection is explicit in config and logs
- backend failures are visible and non-silent
- the code structure is ready for a future second backend without another boundary rewrite

## Future Work

After phase 1 is stable, future iterations can add:

- public partial transcript support
- latency-oriented capture behavior that can exploit partials
- a formal health-check command for external ASR services
- backend capability reporting
- a second backend such as FireRed through the same transcription contract
