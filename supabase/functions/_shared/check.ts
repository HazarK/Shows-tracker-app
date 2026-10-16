/** Compare stored seasons with TMDB and notify each new season once. */

import { newSeasonMessage } from "./messages.ts";
import { newlyReleased } from "./seasons.ts";
import { type ShowDetails } from "./tmdb.ts";

export type CheckResult = {
  checked: number;
  notified: number;
  failed: number;
};

export type TrackedShowRef = {
  id: number;
  telegramChatId: number;
  tmdbId: number;
  title: string;
};

export interface SeasonStore {
  listAllTrackedShows(): Promise<TrackedShowRef[]>;
  seenSeasonNumbers(showId: number): Promise<Set<number>>;
  recordNotifiedSeason(
    showId: number,
    seasonNumber: number,
    airDate: string,
  ): Promise<boolean>;
}

export interface TvCatalog {
  getTv(tmdbId: number): Promise<ShowDetails>;
}

export interface Notifier {
  send(chatId: number, text: string): Promise<void>;
}

export async function checkAll(
  store: SeasonStore,
  tmdb: TvCatalog,
  notifier: Notifier,
  today: string,
): Promise<CheckResult> {
  const shows = await store.listAllTrackedShows();
  if (shows.length === 0) {
    console.info("season check skipped: no tracked shows");
    return { checked: 0, notified: 0, failed: 0 };
  }

  let checked = 0;
  let notified = 0;
  let failed = 0;
  for (const show of shows) {
    checked += 1;
    let details: ShowDetails;
    try {
      details = await tmdb.getTv(show.tmdbId);
    } catch (error) {
      failed += 1;
      console.error(`tmdb lookup failed tmdb_id=${show.tmdbId}`, error);
      continue;
    }

    const seen = await store.seenSeasonNumbers(show.id);
    for (const season of newlyReleased(details.seasons, today)) {
      if (seen.has(season.seasonNumber) || season.airDate === null) {
        continue;
      }
      try {
        await notifier.send(
          show.telegramChatId,
          newSeasonMessage(show.title, season.seasonNumber),
        );
      } catch (error) {
        failed += 1;
        console.error(
          `telegram notify failed tmdb_id=${show.tmdbId} season=${season.seasonNumber}`,
          error,
        );
        continue;
      }
      try {
        const inserted = await store.recordNotifiedSeason(
          show.id,
          season.seasonNumber,
          season.airDate,
        );
        seen.add(season.seasonNumber);
        if (inserted) {
          notified += 1;
        }
      } catch (error) {
        failed += 1;
        console.error(
          `failed to record notification tmdb_id=${show.tmdbId} season=${season.seasonNumber}`,
          error,
        );
      }
    }
  }

  console.info(
    `season check finished checked=${checked} notified=${notified} failed=${failed}`,
  );
  return { checked, notified, failed };
}
