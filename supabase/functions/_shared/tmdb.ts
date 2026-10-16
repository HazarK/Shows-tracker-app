/** Thin TMDB client. TMDB is the source of truth for show and season facts. */

import { type Season } from "./seasons.ts";

const DEFAULT_BASE_URL = "https://api.themoviedb.org/3";

export class TmdbUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TmdbUnavailable";
  }
}

export class ShowNotFound extends Error {
  constructor(path: string) {
    super(path);
    this.name = "ShowNotFound";
  }
}

export type ShowSearchResult = {
  tmdbId: number;
  title: string;
  firstAirYear: number | null;
};

export type ShowDetails = {
  tmdbId: number;
  title: string;
  firstAirYear: number | null;
  seasons: Season[];
};

export interface ShowCatalog {
  searchTv(query: string, limit?: number): Promise<ShowSearchResult[]>;
  getTv(tmdbId: number): Promise<ShowDetails>;
}

export class TmdbClient implements ShowCatalog {
  constructor(
    private readonly apiKey: string,
    private readonly baseUrl = DEFAULT_BASE_URL,
  ) {}

  async searchTv(query: string, limit = 5): Promise<ShowSearchResult[]> {
    let payload: Record<string, unknown>;
    try {
      payload = await this.get("/search/tv", { query });
    } catch (error) {
      if (error instanceof ShowNotFound) {
        throw new TmdbUnavailable("TMDB search failed");
      }
      throw error;
    }
    const rawResults = payload.results;
    if (!Array.isArray(rawResults)) {
      throw new TmdbUnavailable("TMDB search response did not include results");
    }

    const shows: ShowSearchResult[] = [];
    for (const item of rawResults) {
      if (!isRecord(item) || item.id === undefined || typeof item.name !== "string") {
        continue;
      }
      shows.push({
        tmdbId: Number(item.id),
        title: item.name,
        firstAirYear: yearOf(item.first_air_date),
      });
      if (shows.length >= limit) {
        break;
      }
    }
    return shows;
  }

  async getTv(tmdbId: number): Promise<ShowDetails> {
    const payload = await this.get(`/tv/${tmdbId}`);
    const name = payload.name;
    const rawSeasons = payload.seasons;
    if (typeof name !== "string" || !Array.isArray(rawSeasons)) {
      throw new TmdbUnavailable("TMDB show details were incomplete");
    }

    const seasons: Season[] = [];
    for (const item of rawSeasons) {
      if (!isRecord(item) || item.season_number === undefined) {
        continue;
      }
      seasons.push({
        seasonNumber: Number(item.season_number),
        airDate: airDateOf(item.air_date),
      });
    }
    const showId = payload.id ?? tmdbId;
    return {
      tmdbId: Number(showId),
      title: name,
      firstAirYear: yearOf(payload.first_air_date),
      seasons,
    };
  }

  private async get(
    path: string,
    params?: Record<string, string>,
  ): Promise<Record<string, unknown>> {
    const url = new URL(`${this.baseUrl}${path}`);
    url.searchParams.set("api_key", this.apiKey);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
    }

    let response: Response;
    try {
      response = await fetch(url, { signal: AbortSignal.timeout(20_000) });
    } catch {
      throw new TmdbUnavailable("TMDB request failed");
    }
    if (response.status === 404) {
      throw new ShowNotFound(path);
    }
    if (response.status >= 400) {
      throw new TmdbUnavailable(`TMDB returned HTTP ${response.status}`);
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new TmdbUnavailable("TMDB returned invalid JSON");
    }
    if (!isRecord(payload)) {
      throw new TmdbUnavailable("TMDB returned an unexpected payload");
    }
    return payload;
  }
}

function yearOf(value: unknown): number | null {
  if (typeof value !== "string" || value.length < 4) {
    return null;
  }
  const yearText = value.slice(0, 4);
  if (!/^\d{4}$/.test(yearText)) {
    return null;
  }
  return Number(yearText);
}

function airDateOf(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0) {
    return null;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() !== month - 1 ||
    utc.getUTCDate() !== day
  ) {
    return null;
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
