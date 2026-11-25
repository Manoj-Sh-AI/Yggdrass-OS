"""The chat worker's loop must say when it fails (type only), not swallow it silently."""

import logging
import threading

from yggdress_app.agent_worker import AgentWorker


def test_a_failing_lane_is_logged_once_by_type_and_never_by_text(caplog):
    worker = AgentWorker(None, None, None, None, None, "default")
    calls = []

    def tick(lane):
        calls.append(lane)
        if len(calls) >= 3:
            worker.stopped.set()
        raise ConnectionRefusedError("secret-ish detail: postgres://user:pw@host")

    worker.tick = tick
    worker.stopped.wait = lambda _timeout: None  # no sleeping in the test
    with caplog.at_level(logging.ERROR):
        thread = threading.Thread(target=worker.loop, args=("chat",))
        thread.start()
        thread.join(5)
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["Agent chat lane failed (ConnectionRefusedError)"]
    assert "pw@host" not in caplog.text
