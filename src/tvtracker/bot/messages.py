"""User-facing copy. HTML bold is how the PRD's emphasis is sent to Telegram."""

from __future__ import annotations

EMPTY_LIST = "You aren't following any shows yet. Use /add <show name> to add one."
API_UNAVAILABLE = (
    "I couldn't complete that request because the TV database is unavailable. "
    "Please try again later."
)
USAGE_ADD = "Usage: /add <show name>"
USAGE_REMOVE = "Usage: /remove <show name>"
CANCELLED = "Cancelled."
NOTHING_TO_CANCEL = "Nothing to cancel."
CHOICE_EXPIRED = "That choice expired. Please try again."
CHOICE_INVALID = "That choice is no longer valid. Please try again."
PRIVATE_BOT = "This bot isn't available for this chat."
SEVERAL_ADD = "Several shows match. Which one do you want to follow?"
SEVERAL_REMOVE = "Several shows match. Which one do you want to stop following?"
HELP_TEXT = """\
TV Season Tracker follows shows you care about and messages you when a new season is out.

/add <show name> — follow a show
/list — see shows you follow
/remove <show name> — stop following a show
/cancel — dismiss the current choice
/help — show this message"""


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_show(title: str, year: int | None) -> str:
    if year is None:
        return title
    return f"{title} ({year})"


def found_prompt(title: str, year: int | None) -> str:
    shown = escape_html(format_show(title, year))
    return f"I found <b>{shown}</b>. Is this the show you want to follow?"


def remove_prompt(title: str, year: int | None) -> str:
    shown = escape_html(format_show(title, year))
    return f"Stop following <b>{shown}</b>?"


def not_found_message(query: str) -> str:
    return (
        f"I couldn't find a show matching <b>{escape_html(query)}</b>. Try another title."
    )


def new_season_message(title: str, season_number: int) -> str:
    return f"🎬 New season available: {title} — Season {season_number}"


def button_label(title: str, year: int | None) -> str:
    label = format_show(title, year)
    if len(label) <= 60:
        return label
    return label[:57] + "..."
