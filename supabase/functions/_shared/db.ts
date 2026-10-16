/** Postgres access through the Supabase service role. */

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";

import { type Season } from "./seasons.ts";

export class AlreadyTracking extends Error {
  constructor(readonly tmdbId: number) {
    super(`already tracking tmdb id ${tmdbId}`);
    this.name = "AlreadyTracking";
  }
}

export type TrackedShow = {
  id: number;
  telegramChatId: number;
  tmdbId: number;
  title: string;
  firstAirYear: number | null;
};

export type PendingPayload = {
  tmdb_ids?: number[];
  show_ids?: number[];
};

export type PendingChoice = {
  action: string;
  payload: PendingPayload;
  expiresAt: Date;
};

type ShowRow = {
  id: number | string;
  tmdb_id: number | string;
  title: string;
  first_air_year: number | string | null;
  user_id?: number | string;
};

export function createServiceClient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL")?.trim() ?? "";
  const key = (
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ??
      Deno.env.get("SUPABASE_SECRET_KEY") ??
      ""
  ).trim();
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required");
  }
  return createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
}

export class Database {
  constructor(private readonly supabase: SupabaseClient) {}

  async listTrackedShows(chatId: number): Promise<TrackedShow[]> {
    const userId = await this.userId(chatId);
    if (userId === null) {
      return [];
    }
    const { data, error } = await this.supabase
      .from("tracked_shows")
      .select("id, tmdb_id, title, first_air_year")
      .eq("user_id", userId);
    if (error) {
      throw new Error(error.message);
    }
    return ((data ?? []) as ShowRow[])
      .map((row) => this.toShow(row, chatId))
      .sort((left, right) => {
        const byTitle = left.title.localeCompare(right.title, undefined, {
          sensitivity: "accent",
        });
        if (byTitle !== 0) {
          return byTitle;
        }
        return left.id - right.id;
      });
  }

  async listAllTrackedShows(): Promise<TrackedShow[]> {
    const { data, error } = await this.supabase
      .from("tracked_shows")
      .select("id, user_id, tmdb_id, title, first_air_year")
      .order("id");
    if (error) {
      throw new Error(error.message);
    }
    const rows = (data ?? []) as ShowRow[];
    if (rows.length === 0) {
      return [];
    }
    const userIds = [...new Set(rows.map((row) => asInt(row.user_id)))];
    const { data: users, error: userError } = await this.supabase
      .from("users")
      .select("id, telegram_chat_id")
      .in("id", userIds);
    if (userError) {
      throw new Error(userError.message);
    }
    const chatByUser = new Map<number, number>();
    for (const user of users ?? []) {
      chatByUser.set(asInt(user.id), asInt(user.telegram_chat_id));
    }
    return rows.map((row) => {
      const chatId = chatByUser.get(asInt(row.user_id));
      if (chatId === undefined) {
        throw new Error(`user missing for tracked show ${row.id}`);
      }
      return this.toShow(row, chatId);
    });
  }

  async findTrackedByTitle(chatId: number, query: string): Promise<TrackedShow[]> {
    const shows = await this.listTrackedShows(chatId);
    const needle = query.toLowerCase().trim();
    const exact = shows.filter((show) => show.title.toLowerCase() === needle);
    if (exact.length > 0) {
      return exact;
    }
    return shows.filter((show) => show.title.toLowerCase().includes(needle));
  }

  async getTrackedShow(chatId: number, showId: number): Promise<TrackedShow | null> {
    const userId = await this.userId(chatId);
    if (userId === null) {
      return null;
    }
    const { data, error } = await this.supabase
      .from("tracked_shows")
      .select("id, tmdb_id, title, first_air_year")
      .eq("id", showId)
      .eq("user_id", userId)
      .maybeSingle();
    if (error) {
      throw new Error(error.message);
    }
    if (!data) {
      return null;
    }
    return this.toShow(data as ShowRow, chatId);
  }

  async addTrackedShow(
    chatId: number,
    show: {
      tmdbId: number;
      title: string;
      firstAirYear: number | null;
      baselineSeasons: Season[];
    },
  ): Promise<void> {
    const baseline = new Map<number, Season>();
    for (const season of show.baselineSeasons) {
      if (!baseline.has(season.seasonNumber)) {
        baseline.set(season.seasonNumber, season);
      }
    }
    const { error } = await this.supabase.rpc("add_tracked_show", {
      p_telegram_chat_id: chatId,
      p_tmdb_id: show.tmdbId,
      p_title: show.title,
      p_first_air_year: show.firstAirYear,
      p_baseline: [...baseline.values()].map((season) => ({
        season_number: season.seasonNumber,
        air_date: season.airDate,
      })),
    });
    if (error) {
      if (error.message.includes("already_tracking") || error.code === "P0001") {
        throw new AlreadyTracking(show.tmdbId);
      }
      throw new Error(error.message);
    }
  }

  async removeTrackedShow(chatId: number, showId: number): Promise<boolean> {
    const userId = await this.userId(chatId);
    if (userId === null) {
      return false;
    }
    const { data, error } = await this.supabase
      .from("tracked_shows")
      .delete()
      .eq("id", showId)
      .eq("user_id", userId)
      .select("id");
    if (error) {
      throw new Error(error.message);
    }
    return (data ?? []).length === 1;
  }

  async seenSeasonNumbers(showId: number): Promise<Set<number>> {
    const { data, error } = await this.supabase
      .from("seen_seasons")
      .select("season_number")
      .eq("tracked_show_id", showId);
    if (error) {
      throw new Error(error.message);
    }
    return new Set((data ?? []).map((row) => asInt(row.season_number)));
  }

  async recordNotifiedSeason(
    showId: number,
    seasonNumber: number,
    airDate: string,
  ): Promise<boolean> {
    const { error } = await this.supabase.from("seen_seasons").insert({
      tracked_show_id: showId,
      season_number: seasonNumber,
      air_date: airDate,
      status: "notified",
      notified_at: new Date().toISOString(),
    });
    if (error?.code === "23505") {
      return false;
    }
    if (error) {
      throw new Error(error.message);
    }
    return true;
  }

  async setPendingChoice(
    chatId: number,
    action: "add" | "remove",
    payload: PendingPayload,
    expiresAt: Date,
  ): Promise<void> {
    const { error } = await this.supabase.from("pending_choices").upsert(
      {
        telegram_chat_id: chatId,
        action,
        payload,
        expires_at: expiresAt.toISOString(),
      },
      { onConflict: "telegram_chat_id" },
    );
    if (error) {
      throw new Error(error.message);
    }
  }

  async getPendingChoice(chatId: number, now: Date): Promise<PendingChoice | null> {
    const { data, error } = await this.supabase
      .from("pending_choices")
      .select("action, payload, expires_at")
      .eq("telegram_chat_id", chatId)
      .maybeSingle();
    if (error) {
      throw new Error(error.message);
    }
    if (!data) {
      return null;
    }
    const expiresAt = new Date(data.expires_at);
    if (expiresAt.getTime() <= now.getTime()) {
      await this.clearPendingChoice(chatId);
      return null;
    }
    return {
      action: String(data.action),
      payload: (data.payload ?? {}) as PendingPayload,
      expiresAt,
    };
  }

  async clearPendingChoice(chatId: number): Promise<void> {
    const { error } = await this.supabase
      .from("pending_choices")
      .delete()
      .eq("telegram_chat_id", chatId);
    if (error) {
      throw new Error(error.message);
    }
  }

  private async userId(chatId: number): Promise<number | null> {
    const { data, error } = await this.supabase
      .from("users")
      .select("id")
      .eq("telegram_chat_id", chatId)
      .maybeSingle();
    if (error) {
      throw new Error(error.message);
    }
    if (!data) {
      return null;
    }
    return asInt(data.id);
  }

  private toShow(row: ShowRow, chatId: number): TrackedShow {
    return {
      id: asInt(row.id),
      telegramChatId: chatId,
      tmdbId: asInt(row.tmdb_id),
      title: row.title,
      firstAirYear: row.first_air_year === null ? null : asInt(row.first_air_year),
    };
  }
}

function asInt(value: number | string | undefined): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isSafeInteger(parsed)) {
    throw new Error("expected an integer id");
  }
  return parsed;
}
