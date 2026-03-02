# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Worker lifecycle protocol unified with `WorkerHandle` and `is_alive` checks.
- Runtime health monitoring now records fatal worker exits.
- Shared queue overflow utility `put_nowait_or_drop`.
- End-to-end GPT-SoVITS-gated audio pipeline test.
- Non-blocking CI quality jobs for `pyright` and coverage.
- MIT license and contribution documentation.

### Changed
- `AppConfig` is immutable (`frozen=True`) with post-init validation.
- Queue full handling is DRYed across runtime workers.
- Ruff docstring lint (`D`, Google convention) enabled in staged mode.

### Fixed
- ASR worker engine start is idempotent.
- Runtime loop now handles worker failure with explicit fatal state.
