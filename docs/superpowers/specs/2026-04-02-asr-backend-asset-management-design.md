# VoxKeep ASR Backend And Asset Management Design

## Context

VoxKeep currently depends on FunASR as a critical ASR backend, but the dependency is managed in a non-reproducible way:

- historical startup relied on a user-specific local path under `/home/user/workspace/FunASR`
- the current default Docker image name `gpudokerasr` is not a verifiable public artifact
- runtime behavior mixes backend selection, service management, and connection details

This makes host migration, environment rebuilds, and support difficult. The goal is to replace that with a reproducible, inspectable, and user-controllable backend model closer to how desktop apps like Handy manage heavyweight speech assets.

## Goals

- Support a `Hybrid` backend strategy:
  - prefer an already-running healthy external backend
  - fall back to managed local backend startup when configured assets are available
- Separate VoxKeep runtime logic from backend-specific deployment details
- Make backend artifacts reproducible:
  - explicit image references
  - explicit model directories
  - explicit startup commands
  - explicit health checks
- Make heavyweight dependencies user-manageable:
  - install
  - inspect
  - start
  - stop
  - disable
  - remove
  - purge
- Keep large models and runtime assets out of the repository working tree

## Non-Goals

- Do not implement a general package manager for arbitrary ML frameworks
- Do not bundle large ASR models into the Git repository
- Do not add hidden automatic downloads during normal `run` unless the user explicitly requested managed local setup
- Do not remove support for external FunASR-compatible services

## Design Summary

VoxKeep should be split into three concerns:

1. `ASR runtime contract`
   - the capture/transcription pipeline depends only on a stable backend interface
2. `Backend registry`
   - metadata for each backend, including transport, capabilities, assets, startup mode, and health checks
3. `Asset and service manager`
   - manages installed assets and optional managed local runtime lifecycle

The runtime should no longer care whether a backend is:

- an external WebSocket service
- a Docker-managed local service
- a future local in-process backend

The runtime only asks for:

- resolved backend selection
- a reachable endpoint or backend handle
- health status

## Architecture

### 1. Backend Contract Layer

Introduce an internal backend abstraction that the transcription module can consume without knowing deployment details.

Expected responsibilities:

- identify active backend
- expose connection details needed by runtime
- report readiness and degraded state
- surface backend-specific failure reasons in a normalized form

For the current FunASR WebSocket path, the transcription runtime still connects to a WebSocket endpoint, but endpoint discovery should come from backend resolution rather than directly from static config defaults.

### 2. Backend Registry

Add a registry describing each supported ASR backend.

Each backend definition should include:

- `backend_id`
- `display_name`
- `kind`
  - `external_service`
  - `managed_service`
  - `inprocess`
- `transport`
  - `websocket`
  - `http`
  - `local`
- `capabilities`
  - streaming support
  - final-only support
  - language selection support
  - GPU support
  - CPU fallback support
- `asset_requirements`
  - image reference, digest, or build recipe
  - model names, versions, checksums, and storage paths
  - environment requirements such as CUDA or CPU-only support
- `service_definition`
  - startup command template
  - container or process manager type
  - default port bindings
  - logs location
- `healthcheck_definition`
  - TCP reachability
  - protocol handshake
  - optional minimal inference-level readiness check
- `cleanup_definition`
  - removable runtime files
  - removable caches
  - removable models

The initial registry should include at least:

- `funasr_ws_external`
- `funasr_ws_managed`

These may point to the same runtime protocol but differ in ownership and startup behavior.

### 3. Asset Manager

Manage heavyweight backend assets outside the repository tree.

Recommended directories:

- config: `~/.config/voxkeep/`
- shared data: `~/.local/share/voxkeep/`
- runtime state: `~/.local/state/voxkeep/`

Recommended structure:

```text
~/.config/voxkeep/
  config.yaml

~/.local/share/voxkeep/
  backends/
    registry.json
    installed.json
  models/
    funasr/
      <model-version>/
    whisper/
      <model-file-or-dir>

~/.local/state/voxkeep/
  services/
    funasr/
      pid
      endpoint.json
      lease.json
  logs/
    funasr/
      current.log
```

Key rules:

- large models do not live in the Git checkout
- managed service state does not live in the Git checkout
- repository scripts may read and operate on these directories, but should not assume user-specific absolute paths like `/home/user/...`

### 4. Service Manager

The service manager owns optional local backend startup and shutdown.

Supported service ownership modes:

- `external`
  - VoxKeep only connects
  - startup and shutdown are external to VoxKeep
- `managed`
  - VoxKeep starts and stops the backend
- `auto`
  - VoxKeep probes for an external healthy backend first
  - if absent, VoxKeep attempts managed startup

`auto` should be the default user-facing mode for convenience, but actual behavior must remain explicit in logs:

- "using external backend: ..."
- "external backend unavailable; starting managed backend: ..."
- "managed backend unavailable because assets are missing: ..."

### 5. Health Checks

Health checks must be stronger than raw port probing.

For FunASR WebSocket:

1. TCP reachable
2. WebSocket handshake succeeds
3. optional protocol sanity check succeeds, or service reports ready state

Readiness states:

- `healthy`
- `starting`
- `degraded`
- `unavailable`

The runtime should refuse to silently proceed when the configured backend is unavailable. Errors should clearly distinguish:

- missing assets
- image unavailable
- process start failure
- handshake failure
- protocol mismatch

## Configuration Model

Extend configuration from a single FunASR endpoint into backend-oriented settings.

Recommended structure:

```yaml
asr:
  backend: funasr_ws
  mode: auto

  external:
    host: 127.0.0.1
    port: 10096
    path: /
    use_ssl: false

  managed:
    provider: docker
    image: registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13
    image_digest: ""
    service_name: funasr
    expose_port: 10096
    models_dir: ~/.local/share/voxkeep/models/funasr
```

Compatibility handling:

- keep a temporary migration layer from the existing `funasr.*` config fields
- emit a clear warning when legacy config is used
- remove hardcoded `gpudokerasr` defaults

## CLI Surface

Add explicit management commands.

Recommended commands:

- `voxkeep backend list`
- `voxkeep backend current`
- `voxkeep backend use <backend_id>`
- `voxkeep backend doctor`
- `voxkeep asset install <backend_id>`
- `voxkeep asset status <backend_id>`
- `voxkeep asset remove <backend_id>`
- `voxkeep asset purge <backend_id>`
- `voxkeep service start <backend_id>`
- `voxkeep service stop <backend_id>`
- `voxkeep service logs <backend_id>`

Command semantics:

- `install`
  - fetches or validates required artifacts
- `remove`
  - removes managed runtime artifacts but preserves user-selected config unless requested otherwise
- `purge`
  - removes runtime artifacts, models, and caches for that backend

## Current FunASR Recommendation

### Cleanup Recommendation

Do not immediately delete the current FunASR source trees.

Recommended handling now:

- keep `/home/zaviro/workspace/FunASR` as the primary reference and fallback baseline
- keep `/home/user/workspace/FunASR` until the new backend management flow is verified
- after the new flow is verified:
  - archive or remove `/home/user/workspace/FunASR`
  - remove stale trash copies such as `/home/user/.local/share/Trash/files/funasr`

Do not preserve:

- hardcoded runtime dependence on `/home/user/...`
- hardcoded dependence on local image tag `gpudokerasr`

### Deployment Recommendation

Short term:

- restore a reproducible backend path first
- prefer either:
  - official FunASR image with explicit tag or digest
  - explicitly configured local source-backed FunASR process under `/home/zaviro/workspace/FunASR`

Medium term:

- move to the `Hybrid` backend registry plus asset manager design
- make `external` and `managed` first-class options

Long term:

- treat FunASR as a backend package rather than a hidden implementation detail
- allow additional ASR backends to coexist under the same management model

## Recommended Initial Implementation Scope

The first implementation slice should stay narrow:

1. introduce backend-oriented config and keep compatibility with current FunASR settings
2. replace `gpudokerasr` with an explicit validated managed backend definition
3. add `backend doctor` and stronger readiness checks
4. add a small installed-assets state file outside the repo
5. keep only FunASR in scope for the first version

This avoids overbuilding a generic platform before one backend path is working reliably.

## Risks And Mitigations

### Risk: Too Much Framework Too Early

Mitigation:

- start with a registry that supports only FunASR
- keep the interface narrow
- avoid implementing plugin loading in the first version

### Risk: User Confusion Around Auto Mode

Mitigation:

- log backend resolution decisions clearly
- expose `backend current`
- keep `external`, `managed`, and `auto` behavior documented and testable

### Risk: Environment Drift

Mitigation:

- record exact image references and model versions
- verify checksums where possible
- make health checks part of `doctor`

### Risk: Silent Degradation

Mitigation:

- preserve the current rule that backend fallback must emit a clear log message
- do not silently swap from one backend family to another

## Testing Strategy

High-frequency:

- unit tests for backend resolution
- unit tests for registry parsing and validation
- unit tests for healthcheck state mapping

Change-triggered:

- integration tests for managed startup flow
- integration tests for external-versus-managed resolution
- CLI tests for install/status/start/stop/error messages

Low-frequency:

- end-to-end tests against a real FunASR service or fixture-compatible staging backend

## Migration Plan

1. keep current runtime behavior available during transition
2. add backend registry and config compatibility layer
3. switch runtime startup to resolved backend settings
4. add CLI and doctor support
5. deprecate direct legacy FunASR fields and non-reproducible defaults

## Decision

Adopt the `Hybrid Control Plane` model:

- external backend preferred when healthy
- managed backend available as fallback or explicit mode
- heavy assets stored in user data directories
- backend definitions explicit and reproducible
- no default dependence on local-only tags or user-specific source paths
