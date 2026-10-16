import { assertEquals } from "jsr:@std/assert@1";

import {
  checkAll,
  type Notifier,
  type SeasonStore,
  type TrackedShowRef,
  type TvCatalog,
} from "./check.ts";
import { newSeasonMessage } from "./messages.ts";
import { type ShowDetails } from "./tmdb.ts";

const TODAY = "2026-10-15";

const SHOW: TrackedShowRef = {
  id: 1,
  telegramChatId: 10,
  tmdbId: 5,
  title: "Severance",
};

Deno.test("empty tracking list does not call tmdb", async () => {
  let lookups = 0;
  const result = await checkAll(
    emptyStore(),
    {
      getTv() {
        lookups += 1;
        return Promise.reject(new Error("should not be called"));
      },
    },
    { send() { return Promise.reject(new Error("should not be called")); } },
    TODAY,
  );

  assertEquals(result, { checked: 0, notified: 0, failed: 0 });
  assertEquals(lookups, 0);
});

Deno.test("already seen seasons are not sent", async () => {
  const seen = new Set<number>([1]);
  const sent: string[] = [];
  const result = await checkAll(
    memoryStore([SHOW], seen),
    catalog(new Map([[5, details([
      { seasonNumber: 0, airDate: "2022-03-25" },
      { seasonNumber: 1, airDate: "2022-02-18" },
      { seasonNumber: 2, airDate: null },
      { seasonNumber: 3, airDate: "2026-12-01" },
      { seasonNumber: 4, airDate: TODAY },
    ])]])),
    recordingNotifier(sent),
    TODAY,
  );

  assertEquals(result, { checked: 1, notified: 1, failed: 0 });
  assertEquals(sent, [newSeasonMessage("Severance", 4)]);
});

Deno.test("a second run does not repeat a notification", async () => {
  const seen = new Set<number>();
  const sent: string[] = [];
  const store = memoryStore([SHOW], seen);
  const tmdb = catalog(new Map([[5, details([
    { seasonNumber: 1, airDate: "2022-02-18" },
    { seasonNumber: 2, airDate: TODAY },
  ])]]));
  const notifier = recordingNotifier(sent);

  const first = await checkAll(store, tmdb, notifier, TODAY);
  const second = await checkAll(store, tmdb, notifier, TODAY);

  assertEquals(first.notified, 2);
  assertEquals(second.notified, 0);
  assertEquals(sent, [
    newSeasonMessage("Severance", 1),
    newSeasonMessage("Severance", 2),
  ]);
});

Deno.test("one show's tmdb failure does not block the next show", async () => {
  const seen = new Set<number>();
  const sent: string[] = [];
  const other: TrackedShowRef = {
    id: 2,
    telegramChatId: 10,
    tmdbId: 8,
    title: "Andor",
  };
  const result = await checkAll(
    memoryStore([SHOW, other], seen),
    {
      getTv(tmdbId: number) {
        if (tmdbId === 5) {
          return Promise.reject(new Error("tmdb down"));
        }
        return Promise.resolve(details([
          { seasonNumber: 1, airDate: "2022-09-21" },
        ], 8, "Andor"));
      },
    },
    recordingNotifier(sent),
    TODAY,
  );

  assertEquals(result, { checked: 2, notified: 1, failed: 1 });
  assertEquals(sent, [newSeasonMessage("Andor", 1)]);
});

Deno.test("a failed send leaves the season unseen", async () => {
  const seen = new Set<number>();
  let recorded = 0;
  const store = memoryStore([SHOW], seen);
  const originalRecord = store.recordNotifiedSeason.bind(store);
  store.recordNotifiedSeason = (showId, seasonNumber, airDate) => {
    recorded += 1;
    return originalRecord(showId, seasonNumber, airDate);
  };
  const result = await checkAll(
    store,
    catalog(new Map([[5, details([{ seasonNumber: 1, airDate: "2022-02-18" }])]])),
    { send() { return Promise.reject(new Error("telegram down")); } },
    TODAY,
  );

  assertEquals(result.notified, 0);
  assertEquals(result.failed, 1);
  assertEquals(recorded, 0);
  assertEquals(seen.size, 0);
});

function emptyStore(): SeasonStore {
  return {
    listAllTrackedShows() {
      return Promise.resolve([]);
    },
    seenSeasonNumbers() {
      return Promise.resolve(new Set());
    },
    recordNotifiedSeason() {
      return Promise.resolve(false);
    },
  };
}

function memoryStore(shows: TrackedShowRef[], seen: Set<number>): SeasonStore {
  return {
    listAllTrackedShows() {
      return Promise.resolve(shows);
    },
    seenSeasonNumbers() {
      return Promise.resolve(new Set(seen));
    },
    recordNotifiedSeason(_showId, seasonNumber) {
      if (seen.has(seasonNumber)) {
        return Promise.resolve(false);
      }
      seen.add(seasonNumber);
      return Promise.resolve(true);
    },
  };
}

function catalog(detailsById: Map<number, ShowDetails>): TvCatalog {
  return {
    getTv(tmdbId) {
      const details = detailsById.get(tmdbId);
      if (!details) {
        return Promise.reject(new Error(`missing ${tmdbId}`));
      }
      return Promise.resolve(details);
    },
  };
}

function details(
  seasons: ShowDetails["seasons"],
  tmdbId = 5,
  title = "Severance",
): ShowDetails {
  return { tmdbId, title, firstAirYear: 2022, seasons };
}

function recordingNotifier(sent: string[]): Notifier {
  return {
    send(_chatId, text) {
      sent.push(text);
      return Promise.resolve();
    },
  };
}
