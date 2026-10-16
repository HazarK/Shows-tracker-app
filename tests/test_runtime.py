import asyncio
import logging

from tvtracker.runtime import configure_logging, ensure_event_loop


def test_configure_logging_hides_request_urls():
    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_ensure_event_loop_when_none_is_set():
    previous = None
    try:
        previous = asyncio.get_event_loop()
    except RuntimeError:
        previous = None
    asyncio.set_event_loop(None)
    try:
        loop = ensure_event_loop()
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert not loop.is_closed()
        assert asyncio.get_event_loop() is loop
    finally:
        asyncio.set_event_loop(previous)
