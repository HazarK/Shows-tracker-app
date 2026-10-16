/** Telegram webhook. Wakes on each update and exits. */

import { dispatchUpdate } from "./commands.ts";
import { Database, createServiceClient } from "./db.ts";
import {
  allowedChatIds,
  checkTimezone,
  json,
  requiredSecret,
  secretsMatch,
} from "./http.ts";
import { calendarDate } from "./seasons.ts";
import { TelegramApi } from "./telegram.ts";
import { TmdbClient } from "./tmdb.ts";

export async function handleWebhook(request: Request): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  let expected: string;
  try {
    expected = requiredSecret("TELEGRAM_WEBHOOK_SECRET");
  } catch (error) {
    console.error(error);
    return json({ error: "misconfigured" }, 500);
  }
  if (!secretsMatch(expected, request.headers.get("X-Telegram-Bot-Api-Secret-Token"))) {
    return json({ error: "unauthorized" }, 401);
  }

  let update: unknown;
  try {
    update = await request.json();
  } catch {
    return json({ error: "invalid json" }, 400);
  }

  try {
    const now = new Date();
    const timeZone = checkTimezone();
    const telegram = new TelegramApi(requiredSecret("TELEGRAM_BOT_TOKEN"));
    const callbackQueryId = callbackQueryIdOf(update);
    if (callbackQueryId !== null) {
      try {
        await telegram.answerCallbackQuery(callbackQueryId);
      } catch (error) {
        console.error("answerCallbackQuery failed", error);
      }
    }
    const reply = await dispatchUpdate(update, {
      db: new Database(createServiceClient()),
      tmdb: new TmdbClient(requiredSecret("TMDB_API_KEY")),
      now,
      today: calendarDate(now, timeZone),
      allowed: allowedChatIds(),
    });
    if (reply?.kind === "edit") {
      await telegram.editMessageText(reply.chatId, reply.messageId, reply.outgoing);
    } else if (reply?.kind === "message") {
      await telegram.sendMessage(reply.chatId, reply.outgoing);
    }
  } catch (error) {
    console.error("webhook failed", error);
    return json({ error: "failed" }, 500);
  }
  return json({ ok: true }, 200);
}

function callbackQueryIdOf(update: unknown): string | null {
  if (typeof update !== "object" || update === null || !("callback_query" in update)) {
    return null;
  }
  const query = update.callback_query;
  if (typeof query !== "object" || query === null || !("id" in query)) {
    return null;
  }
  return typeof query.id === "string" ? query.id : null;
}
