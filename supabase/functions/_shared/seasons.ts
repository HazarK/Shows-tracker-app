/** Pure rules for which seasons count as newly released. */

export type Season = {
  seasonNumber: number;
  airDate: string | null;
};

/** Numbered seasons whose premiere date is known and is today or earlier.
 *
 * Season 0 and specials are ignored. A missing or future premiere date is ignored.
 * Duplicate season numbers keep the first occurrence.
 * `today` and `airDate` are `YYYY-MM-DD`.
 */
export function newlyReleased(seasons: Iterable<Season>, today: string): Season[] {
  const chosen = new Map<number, Season>();
  for (const season of seasons) {
    if (
      season.seasonNumber < 1 ||
      season.airDate === null ||
      season.airDate > today
    ) {
      continue;
    }
    if (!chosen.has(season.seasonNumber)) {
      chosen.set(season.seasonNumber, season);
    }
  }
  return [...chosen.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([, season]) => season);
}

/** Calendar date in `timeZone`, as `YYYY-MM-DD`. */
export function calendarDate(now: Date, timeZone: string): string {
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(now);
  } catch (error) {
    if (error instanceof RangeError) {
      throw new Error(`Unknown CHECK_TIMEZONE: ${timeZone}`);
    }
    throw error;
  }
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  const year = value("year");
  const month = value("month");
  const day = value("day");
  if (!year || !month || !day) {
    throw new Error(`Unknown CHECK_TIMEZONE: ${timeZone}`);
  }
  return `${year}-${month}-${day}`;
}
