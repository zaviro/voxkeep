from __future__ import annotations

import queue

from voxkeep.shared.queue_utils import put_nowait_or_drop


def test_put_nowait_or_drop_returns_true_when_enqueued():
    q: queue.Queue[int] = queue.Queue(maxsize=1)

    ok = put_nowait_or_drop(q, 1)

    assert ok is True
    assert q.get_nowait() == 1


def test_put_nowait_or_drop_returns_false_and_calls_on_drop():
    q: queue.Queue[int] = queue.Queue(maxsize=1)
    q.put_nowait(1)
    dropped = 0

    def _on_drop() -> None:
        nonlocal dropped
        dropped += 1

    ok = put_nowait_or_drop(q, 2, on_drop=_on_drop)

    assert ok is False
    assert dropped == 1
