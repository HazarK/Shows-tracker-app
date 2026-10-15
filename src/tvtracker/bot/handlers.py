"""Telegram commands. Decision logic is synchronous so tests can skip the Bot API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from tvtracker.bot.messages import (
    API_UNAVAILABLE,
    CANCELLED,
    CHOICE_EXPIRED,
    CHOICE_INVALID,
    EMPTY_LIST,
    HELP_TEXT,
    NOTHING_TO_CANCEL,
    PRIVATE_BOT,
    SEVERAL_ADD,
    SEVERAL_REMOVE,
    USAGE_ADD,
    USAGE_REMOVE,
    button_label,
    format_show,
    found_prompt,
    not_found_message,
)
from tvtracker.config import Config
from tvtracker.db.repository import AlreadyTracking, PendingChoice, Repository
from tvtracker.domain.seasons import newly_released
from tvtracker.tmdb.client import ShowCatalog, ShowNotFound, TmdbUnavailable

logger = logging.getLogger(__name__)

PENDING_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class Button:
    text: str
    callback_data: str


@dataclass(frozen=True)
class Outgoing:
    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()
    parse_mode: str | None = None


def help_message() -> Outgoing:
    return Outgoing(HELP_TEXT)


def start_message() -> Outgoing:
    return help_message()


def rejection_for(chat_id: int, allowed: frozenset[int] | None) -> Outgoing | None:
    if allowed is None or chat_id in allowed:
        return None
    return Outgoing(PRIVATE_BOT)


def list_shows(chat_id: int, *, repo: Repository) -> Outgoing:
    shows = repo.list_tracked_shows(chat_id)
    if not shows:
        return Outgoing(EMPTY_LIST)
    lines = ["You're following:"]
    for show in shows:
        lines.append(f"• {format_show(show.title, show.first_air_year)}")
    return Outgoing("\n".join(lines))


def add_show(
    chat_id: int,
    query: str,
    *,
    tmdb: ShowCatalog,
    repo: Repository,
    now: datetime,
) -> Outgoing:
    title_query = query.strip()
    if not title_query:
        return Outgoing(USAGE_ADD)
    try:
        results = list(tmdb.search_tv(title_query, limit=5))
    except TmdbUnavailable:
        logger.warning("tmdb unavailable during search")
        return Outgoing(API_UNAVAILABLE)

    repo.clear_pending_choice(chat_id)
    if not results:
        return Outgoing(not_found_message(title_query), parse_mode="HTML")

    if len(results) == 1:
        show = results[0]
        tracked = next(
            (
                item
                for item in repo.list_tracked_shows(chat_id)
                if item.tmdb_id == show.tmdb_id
            ),
            None,
        )
        if tracked is not None:
            return Outgoing(
                f"You're already following {format_show(tracked.title, tracked.first_air_year)}."
            )

    expires_at = now + PENDING_TTL
    repo.set_pending_choice(
        chat_id,
        "add",
        {"tmdb_ids": [result.tmdb_id for result in results]},
        expires_at,
    )
    if len(results) == 1:
        show = results[0]
        return Outgoing(
            found_prompt(show.title, show.first_air_year),
            buttons=(
                (
                    Button("Confirm", f"add:{show.tmdb_id}"),
                    Button("Cancel", "add:cancel"),
                ),
            ),
            parse_mode="HTML",
        )

    rows = tuple(
        (Button(button_label(result.title, result.first_air_year), f"add:{result.tmdb_id}"),)
        for result in results
    )
    return Outgoing(SEVERAL_ADD, buttons=rows + ((Button("Cancel", "add:cancel"),),))


def remove_show(
    chat_id: int,
    query: str,
    *,
    repo: Repository,
    now: datetime,
) -> Outgoing:
    title_query = query.strip()
    if not title_query:
        return Outgoing(USAGE_REMOVE)

    repo.clear_pending_choice(chat_id)
    matches = repo.find_tracked_by_title(chat_id, title_query)
    if not matches:
        return Outgoing(f"You're not following a show matching {title_query}.")
    if len(matches) == 1:
        show = matches[0]
        repo.remove_tracked_show(chat_id, show.id)
        return Outgoing(f"Stopped following {format_show(show.title, show.first_air_year)}.")

    repo.set_pending_choice(
        chat_id,
        "remove",
        {"show_ids": [show.id for show in matches]},
        now + PENDING_TTL,
    )
    rows = tuple(
        (Button(button_label(show.title, show.first_air_year), f"rm:{show.id}"),)
        for show in matches
    )
    return Outgoing(SEVERAL_REMOVE, buttons=rows + ((Button("Cancel", "rm:cancel"),),))


def cancel_pending(chat_id: int, *, repo: Repository, now: datetime) -> Outgoing:
    pending = repo.get_pending_choice(chat_id, now)
    if pending is None:
        return Outgoing(NOTHING_TO_CANCEL)
    repo.clear_pending_choice(chat_id)
    return Outgoing(CANCELLED)


def handle_callback(
    chat_id: int,
    data: str,
    *,
    tmdb: ShowCatalog,
    repo: Repository,
    today: date,
    now: datetime,
) -> Outgoing:
    if data in {"add:cancel", "rm:cancel"}:
        repo.clear_pending_choice(chat_id)
        return Outgoing(CANCELLED)

    pending = repo.get_pending_choice(chat_id, now)
    if pending is None:
        return Outgoing(CHOICE_EXPIRED)
    if data.startswith("add:"):
        return _confirm_add(chat_id, data, pending, tmdb=tmdb, repo=repo, today=today)
    if data.startswith("rm:"):
        return _confirm_remove(chat_id, data, pending, repo=repo)
    return Outgoing(CHOICE_INVALID)


def register_handlers(
    application: Application,
    *,
    repo: Repository,
    tmdb: ShowCatalog,
    config: Config,
) -> None:
    def current_time() -> datetime:
        return datetime.now(config.check_timezone)

    async def reply_command(update: Update, outgoing: Outgoing) -> None:
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            outgoing.text,
            parse_mode=outgoing.parse_mode,
            reply_markup=_keyboard(outgoing.buttons),
        )

    def blocked(chat_id: int) -> Outgoing | None:
        return rejection_for(chat_id, config.allowed_chat_ids)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        chat = update.effective_chat
        if chat is None:
            return
        logger.info("start chat_id=%s", chat.id)
        await reply_command(update, blocked(chat.id) or start_message())

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        chat = update.effective_chat
        if chat is None:
            return
        await reply_command(update, blocked(chat.id) or help_message())

    async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if chat is None:
            return
        denial = blocked(chat.id)
        if denial is not None:
            await reply_command(update, denial)
            return
        await reply_command(
            update,
            add_show(
                chat.id,
                _command_text(context),
                tmdb=tmdb,
                repo=repo,
                now=current_time(),
            ),
        )

    async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        chat = update.effective_chat
        if chat is None:
            return
        denial = blocked(chat.id)
        await reply_command(update, denial or list_shows(chat.id, repo=repo))

    async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if chat is None:
            return
        denial = blocked(chat.id)
        if denial is not None:
            await reply_command(update, denial)
            return
        await reply_command(
            update,
            remove_show(
                chat.id,
                _command_text(context),
                repo=repo,
                now=current_time(),
            ),
        )

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        chat = update.effective_chat
        if chat is None:
            return
        denial = blocked(chat.id)
        if denial is not None:
            await reply_command(update, denial)
            return
        current = current_time()
        await reply_command(
            update,
            cancel_pending(chat.id, repo=repo, now=current),
        )

    async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        query = update.callback_query
        chat = update.effective_chat
        if query is None or chat is None:
            return
        await query.answer()
        denial = blocked(chat.id)
        if denial is not None:
            outgoing = denial
        else:
            current = current_time()
            outgoing = handle_callback(
                chat.id,
                query.data or "",
                tmdb=tmdb,
                repo=repo,
                today=current.date(),
                now=current,
            )
        await query.edit_message_text(
            outgoing.text,
            parse_mode=outgoing.parse_mode,
            reply_markup=_edit_keyboard(outgoing.buttons),
        )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(callback))


def _confirm_add(
    chat_id: int,
    data: str,
    pending: PendingChoice,
    *,
    tmdb: ShowCatalog,
    repo: Repository,
    today: date,
) -> Outgoing:
    tmdb_id = _parse_callback_id(data)
    offered = pending.payload.get("tmdb_ids", [])
    if tmdb_id is None or pending.action != "add" or tmdb_id not in offered:
        return Outgoing(CHOICE_INVALID)
    try:
        details = tmdb.get_tv(tmdb_id)
    except ShowNotFound:
        repo.clear_pending_choice(chat_id)
        return Outgoing("I couldn't find that show anymore. Try another title.")
    except TmdbUnavailable:
        logger.warning("tmdb unavailable during confirm tmdb_id=%s", tmdb_id)
        return Outgoing(API_UNAVAILABLE)

    try:
        repo.add_tracked_show(
            chat_id,
            tmdb_id=details.tmdb_id,
            title=details.title,
            first_air_year=details.first_air_year,
            baseline_seasons=newly_released(details.seasons, today),
        )
    except AlreadyTracking:
        repo.clear_pending_choice(chat_id)
        return Outgoing(
            f"You're already following {format_show(details.title, details.first_air_year)}."
        )
    repo.clear_pending_choice(chat_id)
    return Outgoing(f"You're now following {format_show(details.title, details.first_air_year)}.")


def _confirm_remove(
    chat_id: int,
    data: str,
    pending: PendingChoice,
    *,
    repo: Repository,
) -> Outgoing:
    show_id = _parse_callback_id(data)
    offered = pending.payload.get("show_ids", [])
    if show_id is None or pending.action != "remove" or show_id not in offered:
        return Outgoing(CHOICE_INVALID)
    show = repo.get_tracked_show(chat_id, show_id)
    repo.clear_pending_choice(chat_id)
    if show is None or not repo.remove_tracked_show(chat_id, show_id):
        return Outgoing("That show is no longer in your list.")
    return Outgoing(f"Stopped following {format_show(show.title, show.first_air_year)}.")


def _parse_callback_id(data: str) -> int | None:
    _, _, raw = data.partition(":")
    try:
        return int(raw)
    except ValueError:
        return None


def _command_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    if not context.args:
        return ""
    return " ".join(context.args)


def _keyboard(buttons: tuple[tuple[Button, ...], ...]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(button.text, callback_data=button.callback_data)
                for button in row
            ]
            for row in buttons
        ]
    )


def _edit_keyboard(buttons: tuple[tuple[Button, ...], ...]) -> InlineKeyboardMarkup:
    built = _keyboard(buttons)
    if built is None:
        return InlineKeyboardMarkup([])
    return built
