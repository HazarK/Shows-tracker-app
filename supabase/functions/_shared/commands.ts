/** Command decisions. The webhook turns the result into a Telegram API call. */

import {
  AlreadyTracking,
  type Database,
  type PendingChoice,
} from "./db.ts";
import {
  API_UNAVAILABLE,
  buttonLabel,
  CANCELLED,
  CHOICE_EXPIRED,
  CHOICE_INVALID,
  EMPTY_LIST,
  formatShow,
  foundPrompt,
  HELP_TEXT,
  notFoundMessage,
  NOTHING_TO_CANCEL,
  PRIVATE_BOT,
  removePrompt,
  SEVERAL_ADD,
  SEVERAL_REMOVE,
  USAGE_ADD,
  USAGE_REMOVE,
} from "./messages.ts";
import { newlyReleased } from "./seasons.ts";
import { type Button, type Outgoing } from "./telegram.ts";
import {
  ShowNotFound,
  TmdbUnavailable,
  type ShowCatalog,
} from "./tmdb.ts";

const PENDING_TTL_MS = 15 * 60 * 1000;

export type Reply =
  | { kind: "message"; chatId: number; outgoing: Outgoing }
  | {
    kind: "edit";
    chatId: number;
    messageId: number;
    callbackQueryId: string;
    outgoing: Outgoing;
  };

type TelegramMessage = {
  text?: string;
  chat?: { id?: number };
};

type TelegramUpdate = {
  message?: TelegramMessage;
  callback_query?: {
    id?: string;
    data?: string;
    message?: {
      message_id?: number;
      chat?: { id?: number };
    };
  };
};

export async function dispatchUpdate(
  update: unknown,
  deps: {
    db: Database;
    tmdb: ShowCatalog;
    now: Date;
    today: string;
    allowed: Set<number> | null;
  },
): Promise<Reply | null> {
  if (!isRecord(update)) {
    return null;
  }
  const parsed = update as TelegramUpdate;
  if (parsed.callback_query) {
    return await handleCallback(parsed, deps);
  }
  if (parsed.message) {
    return await handleMessage(parsed.message, deps);
  }
  return null;
}

async function handleMessage(
  message: TelegramMessage,
  deps: {
    db: Database;
    tmdb: ShowCatalog;
    now: Date;
    allowed: Set<number> | null;
  },
): Promise<Reply | null> {
  const chatId = message.chat?.id;
  const text = message.text;
  if (chatId === undefined || text === undefined) {
    return null;
  }
  const command = parseCommand(text);
  if (command === null) {
    return null;
  }
  if (command.name === "start") {
    console.info(`start chat_id=${chatId}`);
  }
  const denial = rejectionFor(chatId, deps.allowed);
  if (denial) {
    return { kind: "message", chatId, outgoing: denial };
  }

  let outgoing: Outgoing;
  switch (command.name) {
    case "start":
    case "help":
      outgoing = { text: HELP_TEXT };
      break;
    case "add":
      outgoing = await addShow(chatId, command.args, deps);
      break;
    case "list":
      outgoing = await listShows(chatId, deps.db);
      break;
    case "remove":
      outgoing = await removeShow(chatId, command.args, deps);
      break;
    case "cancel":
      outgoing = await cancelPending(chatId, deps);
      break;
    default:
      return null;
  }
  return { kind: "message", chatId, outgoing };
}

async function handleCallback(
  update: TelegramUpdate,
  deps: {
    db: Database;
    tmdb: ShowCatalog;
    now: Date;
    today: string;
    allowed: Set<number> | null;
  },
): Promise<Reply | null> {
  const query = update.callback_query;
  const chatId = query?.message?.chat?.id;
  const messageId = query?.message?.message_id;
  const callbackQueryId = query?.id;
  if (
    query === undefined ||
    chatId === undefined ||
    messageId === undefined ||
    callbackQueryId === undefined
  ) {
    return null;
  }
  const denial = rejectionFor(chatId, deps.allowed);
  const outgoing = denial ??
    await handleCallbackData(chatId, query.data ?? "", deps);
  return {
    kind: "edit",
    chatId,
    messageId,
    callbackQueryId,
    outgoing,
  };
}

function rejectionFor(chatId: number, allowed: Set<number> | null): Outgoing | null {
  if (allowed === null || allowed.has(chatId)) {
    return null;
  }
  return { text: PRIVATE_BOT };
}

async function listShows(chatId: number, db: Database): Promise<Outgoing> {
  const shows = await db.listTrackedShows(chatId);
  if (shows.length === 0) {
    return { text: EMPTY_LIST };
  }
  const lines = ["You're following:"];
  for (const show of shows) {
    lines.push(`• ${formatShow(show.title, show.firstAirYear)}`);
  }
  return { text: lines.join("\n") };
}

async function addShow(
  chatId: number,
  query: string,
  deps: { db: Database; tmdb: ShowCatalog; now: Date },
): Promise<Outgoing> {
  const titleQuery = query.trim();
  if (!titleQuery) {
    return { text: USAGE_ADD };
  }
  let results;
  try {
    results = await deps.tmdb.searchTv(titleQuery, 5);
  } catch (error) {
    if (error instanceof TmdbUnavailable) {
      console.warn("tmdb unavailable during search");
      return { text: API_UNAVAILABLE };
    }
    throw error;
  }

  await deps.db.clearPendingChoice(chatId);
  if (results.length === 0) {
    return { text: notFoundMessage(titleQuery), parseMode: "HTML" };
  }

  if (results.length === 1) {
    const show = results[0];
    const tracked = (await deps.db.listTrackedShows(chatId)).find(
      (item) => item.tmdbId === show.tmdbId,
    );
    if (tracked) {
      return {
        text: `You're already following ${formatShow(tracked.title, tracked.firstAirYear)}.`,
      };
    }
  }

  await deps.db.setPendingChoice(
    chatId,
    "add",
    { tmdb_ids: results.map((result) => result.tmdbId) },
    new Date(deps.now.getTime() + PENDING_TTL_MS),
  );
  if (results.length === 1) {
    const show = results[0];
    return {
      text: foundPrompt(show.title, show.firstAirYear),
      parseMode: "HTML",
      buttons: [[
        { text: "Confirm", callbackData: `add:${show.tmdbId}` },
        { text: "Cancel", callbackData: "add:cancel" },
      ]],
    };
  }

  const rows: Button[][] = results.map((result) => [
    {
      text: buttonLabel(result.title, result.firstAirYear),
      callbackData: `add:${result.tmdbId}`,
    },
  ]);
  rows.push([{ text: "Cancel", callbackData: "add:cancel" }]);
  return { text: SEVERAL_ADD, buttons: rows };
}

async function removeShow(
  chatId: number,
  query: string,
  deps: { db: Database; now: Date },
): Promise<Outgoing> {
  const titleQuery = query.trim();
  if (!titleQuery) {
    return { text: USAGE_REMOVE };
  }

  await deps.db.clearPendingChoice(chatId);
  const matches = await deps.db.findTrackedByTitle(chatId, titleQuery);
  if (matches.length === 0) {
    return { text: `You're not following a show matching ${titleQuery}.` };
  }
  if (matches.length === 1) {
    const show = matches[0];
    await deps.db.setPendingChoice(
      chatId,
      "remove",
      { show_ids: [show.id] },
      new Date(deps.now.getTime() + PENDING_TTL_MS),
    );
    return {
      text: removePrompt(show.title, show.firstAirYear),
      parseMode: "HTML",
      buttons: [[
        { text: "Confirm", callbackData: `rm:${show.id}` },
        { text: "Cancel", callbackData: "rm:cancel" },
      ]],
    };
  }

  await deps.db.setPendingChoice(
    chatId,
    "remove",
    { show_ids: matches.map((show) => show.id) },
    new Date(deps.now.getTime() + PENDING_TTL_MS),
  );
  const rows: Button[][] = matches.map((show) => [
    {
      text: buttonLabel(show.title, show.firstAirYear),
      callbackData: `rm:${show.id}`,
    },
  ]);
  rows.push([{ text: "Cancel", callbackData: "rm:cancel" }]);
  return { text: SEVERAL_REMOVE, buttons: rows };
}

async function cancelPending(
  chatId: number,
  deps: { db: Database; now: Date },
): Promise<Outgoing> {
  const pending = await deps.db.getPendingChoice(chatId, deps.now);
  if (pending === null) {
    return { text: NOTHING_TO_CANCEL };
  }
  await deps.db.clearPendingChoice(chatId);
  return { text: CANCELLED };
}

async function handleCallbackData(
  chatId: number,
  data: string,
  deps: { db: Database; tmdb: ShowCatalog; today: string; now: Date },
): Promise<Outgoing> {
  if (data === "add:cancel" || data === "rm:cancel") {
    await deps.db.clearPendingChoice(chatId);
    return { text: CANCELLED };
  }

  const pending = await deps.db.getPendingChoice(chatId, deps.now);
  if (pending === null) {
    return { text: CHOICE_EXPIRED };
  }
  if (data.startsWith("add:")) {
    return await confirmAdd(chatId, data, pending, deps);
  }
  if (data.startsWith("rm:")) {
    return await confirmRemove(chatId, data, pending, deps.db);
  }
  return { text: CHOICE_INVALID };
}

async function confirmAdd(
  chatId: number,
  data: string,
  pending: PendingChoice,
  deps: { db: Database; tmdb: ShowCatalog; today: string },
): Promise<Outgoing> {
  const tmdbId = parseCallbackId(data);
  const offered = numberList(pending.payload.tmdb_ids);
  if (tmdbId === null || pending.action !== "add" || !offered.includes(tmdbId)) {
    return { text: CHOICE_INVALID };
  }
  let details;
  try {
    details = await deps.tmdb.getTv(tmdbId);
  } catch (error) {
    if (error instanceof ShowNotFound) {
      await deps.db.clearPendingChoice(chatId);
      return { text: "I couldn't find that show anymore. Try another title." };
    }
    if (error instanceof TmdbUnavailable) {
      console.warn(`tmdb unavailable during confirm tmdb_id=${tmdbId}`);
      return { text: API_UNAVAILABLE };
    }
    throw error;
  }

  try {
    await deps.db.addTrackedShow(chatId, {
      tmdbId: details.tmdbId,
      title: details.title,
      firstAirYear: details.firstAirYear,
      baselineSeasons: newlyReleased(details.seasons, deps.today),
    });
  } catch (error) {
    if (error instanceof AlreadyTracking) {
      await deps.db.clearPendingChoice(chatId);
      return {
        text: `You're already following ${formatShow(details.title, details.firstAirYear)}.`,
      };
    }
    throw error;
  }
  await deps.db.clearPendingChoice(chatId);
  return {
    text: `You're now following ${formatShow(details.title, details.firstAirYear)}.`,
  };
}

async function confirmRemove(
  chatId: number,
  data: string,
  pending: PendingChoice,
  db: Database,
): Promise<Outgoing> {
  const showId = parseCallbackId(data);
  const offered = numberList(pending.payload.show_ids);
  if (showId === null || pending.action !== "remove" || !offered.includes(showId)) {
    return { text: CHOICE_INVALID };
  }
  const show = await db.getTrackedShow(chatId, showId);
  await db.clearPendingChoice(chatId);
  if (show === null || !await db.removeTrackedShow(chatId, showId)) {
    return { text: "That show is no longer in your list." };
  }
  return { text: `Stopped following ${formatShow(show.title, show.firstAirYear)}.` };
}

function parseCallbackId(data: string): number | null {
  const raw = data.slice(data.indexOf(":") + 1);
  if (!/^-?\d+$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed)) {
    return null;
  }
  return parsed;
}

function numberList(value: number[] | undefined): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => Number(item)).filter((item) => Number.isSafeInteger(item));
}

function parseCommand(text: string): { name: string; args: string } | null {
  const match = text.match(/^\/([A-Za-z0-9_]+)(?:@[A-Za-z0-9_]+)?(?:\s([\s\S]*))?$/);
  if (!match) {
    return null;
  }
  const args = (match[2] ?? "").trim().split(/\s+/).filter(Boolean).join(" ");
  return { name: match[1].toLowerCase(), args };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
