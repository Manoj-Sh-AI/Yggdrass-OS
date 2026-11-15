import { describe, expect, it, vi } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { seed } from "../src/lib/data";
import {
  clockParts,
  fetchWeather,
  isWeather,
  sceneKeys,
  seasonFor,
  selectScene,
  type Weather,
} from "../src/lib/scenes";
const now = new Date("2026-11-08T12:00:00Z"),
  prefs = seed(now).preferences;
const weather: Weather = {
  fetchedAt: now.getTime(),
  temperature: 10,
  code: 0,
  sunrise: "2026-11-08T07:00",
  sunset: "2026-11-08T17:00",
  daylight: 36000,
  isDay: true,
  timezone: "Europe/Berlin",
  latitude: 53.55,
  longitude: 9.99,
};
describe("scenery selection", () => {
  it("rejects malformed cached weather and unknown timezones", () => {
    expect(isWeather({ ...weather, timezone: "Invalid/Zone" })).toBe(false);
    expect(isWeather({ ...weather, sunrise: null })).toBe(false);
    expect(isWeather({ ...weather, temperature: undefined })).toBe(false);
  });
  it("normalizes missing polar sunrise times without crashing", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: true,
          json: async () => ({
            timezone: "Europe/Oslo",
            current: { temperature_2m: -5, weather_code: 71, is_day: 0 },
            daily: { sunrise: [null], sunset: [null], daylight_duration: [0] },
          }),
        }),
    );
    try {
      const result = await fetchWeather(78, 15);
      expect(result.sunrise).toBe("");
      expect(
        selectScene(
          new Date(),
          {
            ...prefs,
            place: {
              name: "Polar",
              latitude: 78,
              longitude: 15,
              timezone: "Europe/Oslo",
            },
          },
          result,
        ).phase,
      ).toBe("night");
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it.each([
    [0, "winter"],
    [2, "spring"],
    [5, "summer"],
    [8, "autumn"],
    [11, "winter"],
  ] as const)("maps northern month %s to %s", (m, s) =>
    expect(seasonFor(m, 53)).toBe(s),
  );
  it("reverses southern hemisphere seasons", () => {
    expect(seasonFor(0, -30)).toBe("summer");
    expect(seasonFor(5, -30)).toBe("winter");
  });
  it.each([
    ["05:59", "night"],
    ["06:00", "sunrise"],
    ["08:59", "sunrise"],
    ["09:00", "afternoon"],
    ["16:59", "afternoon"],
    ["17:00", "night"],
  ] as const)("handles sun boundary %s", (time, phase) => {
    const date = new Date(`2026-11-08T${time}:00+01:00`);
    expect(
      selectScene(date, prefs, { ...weather, fetchedAt: date.getTime() }).phase,
    ).toBe(phase);
  });
  it("uses the location timezone over the machine timezone", () => {
    expect(clockParts(now, "Asia/Tokyo").minutes).toBe(21 * 60);
  });
  it("uses clear fallback after two hours and avoids stale sun dates", () => {
    const late = new Date("2026-11-09T12:00:00Z");
    const scene = selectScene(late, prefs, { ...weather, code: 61 });
    expect(scene.sky).toBe("clear");
    expect(scene.phase).toBe("afternoon");
  });
  it("uses matching cached weather for up to two hours", () =>
    expect(
      selectScene(new Date(now.getTime() + 3600000), prefs, {
        ...weather,
        code: 61,
      }).sky,
    ).toBe("rainy"));
  it("ignores weather for a previous location", () =>
    expect(
      selectScene(now, prefs, { ...weather, latitude: -30, code: 61 }).sky,
    ).toBe("clear"));
  it("shows rain for thunderstorms and adds snow only for snow codes", () => {
    expect(selectScene(now, prefs, { ...weather, code: 95 }).sky).toBe("rainy");
    expect(selectScene(now, prefs, { ...weather, code: 73 })).toMatchObject({
      sky: "rainy",
      snow: true,
    });
    expect(
      selectScene(now, { ...prefs, sky: "clear" }, { ...weather, code: 73 })
        .snow,
    ).toBe(false);
  });
  it("allows all three independent manual overrides", () =>
    expect(
      selectScene(
        now,
        { ...prefs, season: "summer", phase: "night", sky: "rainy" },
        weather,
      ).key,
    ).toBe("summer-night-rainy"));
  it("handles polar night and midnight sun", () => {
    expect(
      selectScene(now, prefs, { ...weather, daylight: 0, isDay: false }).phase,
    ).toBe("night");
    expect(
      selectScene(now, prefs, { ...weather, daylight: 86400, isDay: true })
        .phase,
    ).toBe("afternoon");
  });
  it("has 24 unique scenes, each with three real responsive assets", () => {
    expect(new Set(sceneKeys).size).toBe(24);
    const manifest = JSON.parse(
      readFileSync("public/scenes/manifest.json", "utf8"),
    );
    expect(manifest.scenes).toHaveLength(24);
    for (const key of sceneKeys) {
      const scene = manifest.scenes.find((s: { key: string }) => s.key === key);
      expect(scene.variants.map((v: { width: number }) => v.width)).toEqual([
        480, 960, 1920,
      ]);
      for (const asset of scene.variants) {
        expect(existsSync(`public${asset.src}`)).toBe(true);
        expect(asset.bytes).toBeGreaterThan(1000);
      }
    }
  });
});
