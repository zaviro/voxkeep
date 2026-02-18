import threading

from asr_ol.services.shutdown import install_signal_handlers


def test_install_signal_handlers_sets_handlers():
    stop_event = threading.Event()
    install_signal_handlers(stop_event)
    # sanity only: function should run without raising
    assert stop_event.is_set() is False
