"""Process setup shared by the bot and the one-shot season check."""

from __future__ import annotations

import asyncio
import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx logs full request URLs, which include the bot token and TMDB key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Return a loop for python-telegram-bot 21.

    Python 3.14 no longer creates a loop implicitly, and that library still asks for one.
    """
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
