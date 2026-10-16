/** Daily season check. Wakes from cron and exits. */

import { checkAll } from "./check.ts";
import { Database, createServiceClient } from "./db.ts";
import {
  checkTimezone,
  json,
  requiredSecret,
  secretsMatch,
} from "./http.ts";
import { calendarDate } from "./seasons.ts";
import { TelegramApi } from "./telegram.ts";
import { TmdbClient } from "./tmdb.ts";

export async function handleCheck(request: Request): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  let expected: string;
  try {
    expected = requiredSecret("CRON_SECRET");
  } catch (error) {
    console.error(error);
    return json({ error: "misconfigured" }, 500);
  }
  if (!secretsMatch(expected, request.headers.get("x-cron-secret"))) {
    return json({ error: "unauthorized" }, 401);
  }

  try {
    const today = calendarDate(new Date(), checkTimezone());
    const db = new Database(createServiceClient());
    const result = await checkAll(
      db,
      new TmdbClient(requiredSecret("TMDB_API_KEY")),
      new TelegramApi(requiredSecret("TELEGRAM_BOT_TOKEN")),
      today,
    );
    return json(result, 200);
  } catch (error) {
    console.error("season check failed", error);
    return json({ error: "failed" }, 500);
  }
}
