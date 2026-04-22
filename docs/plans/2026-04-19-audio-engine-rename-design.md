# Design Doc: Runtime Module Rename to Audio Engine

## 1. Problem Statement
The term `runtime` is overloaded in the current codebase. It refers to:
1.  `src/voxkeep/modules/runtime/`: Lower-level audio capture and processing.
2.  `src/voxkeep/bootstrap/runtime_app.py`: The overall application orchestration (`AppRuntime`).
This conflict makes navigation and conceptual understanding harder for new developers.

## 2. Proposed Solution
Rename the low-level module from `runtime` to `audio_engine` to better reflect its responsibility as the "engine" driving audio data into the system.

### 2.1 Proposed Changes
- **Directory**: `src/voxkeep/modules/runtime/` -> `src/voxkeep/modules/audio_engine/`
- **Imports**: Update all references in `bootstrap/runtime_app.py`, `cli/`, and tests.
- **Config**: (If following the config decomposition doc) Rename `RuntimeConfig` to `AudioEngineConfig`.
- **Naming**: Ensure `AudioBus` and `AudioSource` remain the primary symbols within this module.

### 2.2 Implementation Strategy
1.  **Preparation**: Ensure a clean git state.
2.  **Rename**: Use `git mv` to move the directory to maintain history.
3.  **Global Replace**: Update import statements across the codebase.
4.  **Refactor Test Layout**: Move `tests/unit/modules/runtime/` to `tests/unit/modules/audio_engine/`.
5.  **Validation**: Run `make test-architecture` to confirm no boundary violations occurred during the rename.

## 3. Success Criteria
- The codebase no longer has two different concepts named "runtime".
- The low-level audio logic is clearly isolated under a descriptive name.
