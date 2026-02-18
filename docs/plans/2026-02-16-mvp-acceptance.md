# MVP Acceptance Checklist

## 1) Continuous ASR persistence
1. Start runtime: `scripts/run_local.sh`
2. Speak continuously for 10 minutes.
3. Query sqlite:
   - `sqlite3 data/asr.db "select count(*), min(start_ts), max(end_ts) from asr_segments where source='stream' and is_final=1;"`
4. Expected:
   - count > 0
   - max(end_ts) increases over time

## 2) Wake + one sentence + one-time inject
1. Focus a text input (terminal/editor).
2. Speak: wake word + one sentence.
3. Expected:
   - text is injected once only, no auto enter
   - `source='capture'` has exactly one new final row for this utterance

## 3) ASR does not depend on wake
1. Start runtime and speak without wake.
2. Expected:
   - stream final rows continue growing
   - no injection occurs

## 4) Mis-wake robustness
1. Trigger repeated wake rapidly, then speak one sentence.
2. Expected:
   - only one capture finalization and one injection

## 5) Graceful shutdown and immediate restart
1. Press `Ctrl+C`.
2. Restart immediately: `scripts/run_local.sh`
3. Expected:
   - no microphone busy error
   - no sqlite lock error
