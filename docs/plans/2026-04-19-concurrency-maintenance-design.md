# Architectural Decision Record: Maintaining Synchronous Threaded Model

## 1. Context
The current system uses a multi-threaded worker model with `queue.Queue` for inter-module communication. While `asyncio` is often preferred for IO-bound tasks like WebSocket (ASR) and SQLite (Storage), the current implementation is stable and performs adequately for local desktop use.

## 2. Decision
We will **not** migrate to `asyncio` at this stage. We will maintain the existing threaded model to prioritize stability and simplicity.

## 3. Rationale
- **Performance**: The current threaded overhead is negligible on modern Linux desktops for the given audio processing load.
- **Complexity**: An `asyncio` migration would require a fundamental rewrite of the orchestration layer and all module entry points.
- **Dependency Control**: Keeping the system synchronous avoids the complexities of integrating third-party AI libraries (which are often synchronous/blocking) with an async event loop.

## 4. Guardrails for the Future
If asynchronous behavior is required for specific components (e.g., a highly concurrent web API or remote ASR), we will adopt an **Incremental Bridge** approach:
- Encapsulate `asyncio` within a specific worker thread.
- Use `janus` or similar thread-safe async queues for bridging.
- Keep the overall orchestration layer synchronous.

## 5. Status
**Accepted** - Maintaining current threaded architecture.
