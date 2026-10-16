import { assertEquals } from "jsr:@std/assert@1";

import { newlyReleased, type Season } from "./seasons.ts";

const TODAY = "2026-10-15";

Deno.test("newlyReleased keeps numbered seasons on or before today", () => {
  const seasons: Season[] = [
    { seasonNumber: 0, airDate: "2022-03-25" },
    { seasonNumber: 2, airDate: TODAY },
    { seasonNumber: 1, airDate: "2022-02-18" },
    { seasonNumber: 3, airDate: null },
    { seasonNumber: 4, airDate: "2026-12-01" },
    { seasonNumber: 1, airDate: "2020-01-01" },
  ];

  const released = newlyReleased(seasons, TODAY);

  assertEquals(released, [
    { seasonNumber: 1, airDate: "2022-02-18" },
    { seasonNumber: 2, airDate: TODAY },
  ]);
});
