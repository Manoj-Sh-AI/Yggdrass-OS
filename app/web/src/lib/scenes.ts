import type { DayPhase, Preferences, Season, Sky } from "./types";
export const seasons: Season[] = ["spring", "summer", "autumn", "winter"];
export const phases: DayPhase[] = ["sunrise", "afternoon", "night"];
export const skies: Sky[] = ["clear", "rainy"];
export type Weather = {
  fetchedAt: number;
  temperature: number;
  code: number;
  sunrise: string;
  sunset: string;
  timezone: string;
  isDay: boolean;
  daylight: number;
  latitude: number;
  longitude: number;
};
export function isWeather(value: unknown): value is Weather {
  if (!value || typeof value !== "object") return false;
  const w = value as Weather;
  if (
    ![
      w.fetchedAt,
      w.temperature,
      w.code,
      w.daylight,
      w.latitude,
      w.longitude,
    ].every(Number.isFinite) ||
    typeof w.isDay !== "boolean" ||
    typeof w.sunrise !== "string" ||
    typeof w.sunset !== "string" ||
    typeof w.timezone !== "string"
  )
    return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: w.timezone });
  } catch {
    return false;
  }
  return true;
}
export type Scene = {
  season: Season;
  phase: DayPhase;
  sky: Sky;
  snow: boolean;
  key: string;
};
export function seasonFor(month: number, latitude: number): Season {
  const north =
    month >= 2 && month <= 4
      ? 0
      : month >= 5 && month <= 7
        ? 1
        : month >= 8 && month <= 10
          ? 2
          : 3;
  return seasons[(north + (latitude < 0 ? 2 : 0)) % 4];
}
export function clockParts(date: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (key: string) => parts.find((p) => p.type === key)?.value ?? "00";
  return {
    month: Number(get("month")) - 1,
    minutes: Number(get("hour")) * 60 + Number(get("minute")),
    date: `${get("year")}-${get("month")}-${get("day")}`,
  };
}
const minuteOf = (s: string) => {
  const m = s.match(/T(\d{2}):(\d{2})/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};
export function selectScene(
  now: Date,
  prefs: Preferences,
  weather: Weather | null,
): Scene {
  const w =
    weather &&
    now.getTime() - weather.fetchedAt <= 7200000 &&
    now.getTime() >= weather.fetchedAt - 60000 &&
    Math.abs(weather.latitude - prefs.place.latitude) < 0.05 &&
    Math.abs(weather.longitude - prefs.place.longitude) < 0.05
      ? weather
      : null;
  const clock = clockParts(now, w?.timezone || prefs.place.timezone);
  let phase: DayPhase =
    clock.minutes >= 360 && clock.minutes < 540
      ? "sunrise"
      : clock.minutes >= 540 && clock.minutes < 1080
        ? "afternoon"
        : "night";
  if (
    w &&
    w.sunrise.startsWith(clock.date) &&
    w.sunset.startsWith(clock.date)
  ) {
    const rise = minuteOf(w.sunrise),
      set = minuteOf(w.sunset);
    if (w.daylight === 0) phase = "night";
    else if (w.daylight >= 86300) phase = "afternoon";
    else if (Number.isFinite(rise) && Number.isFinite(set))
      phase =
        clock.minutes >= rise - 60 && clock.minutes < Math.min(rise + 120, set)
          ? "sunrise"
          : clock.minutes >= rise + 120 && clock.minutes < set
            ? "afternoon"
            : "night";
  } else if (w && (w.daylight === 0 || w.daylight >= 86300))
    phase = w.isDay ? "afternoon" : "night";
  const snow = !!w && [71, 73, 75, 77, 85, 86].includes(w.code);
  const sky: Sky = w && w.code >= 51 ? "rainy" : "clear";
  const s = {
    season:
      prefs.season === "auto"
        ? seasonFor(clock.month, prefs.place.latitude)
        : prefs.season,
    phase: prefs.phase === "auto" ? phase : prefs.phase,
    sky: prefs.sky === "auto" ? sky : prefs.sky,
    snow: snow && prefs.sky === "auto",
  };
  return { ...s, key: `${s.season}-${s.phase}-${s.sky}` };
}
export const sceneKeys = seasons.flatMap((s) =>
  phases.flatMap((p) => skies.map((w) => `${s}-${p}-${w}`)),
);
export async function fetchWeather(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<Weather> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    current: "temperature_2m,weather_code,is_day",
    daily: "sunrise,sunset,daylight_duration",
    timezone: "auto",
    forecast_days: "1",
  });
  const response = await fetch(
    `https://api.open-meteo.com/v1/forecast?${params}`,
    {
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
        : AbortSignal.timeout(10000),
    },
  );
  if (!response.ok)
    throw new Error(
      "Weather is temporarily unavailable. Your seasonal scene will keep working.",
    );
  const data = await response.json();
  if (!data.current || !data.daily || typeof data.timezone !== "string")
    throw new Error("Weather data is incomplete.");
  const result: Weather = {
    fetchedAt: Date.now(),
    temperature: data.current.temperature_2m,
    code: data.current.weather_code,
    isDay: !!data.current.is_day,
    sunrise: data.daily.sunrise?.[0] ?? "",
    sunset: data.daily.sunset?.[0] ?? "",
    daylight: data.daily.daylight_duration?.[0],
    timezone: data.timezone,
    latitude,
    longitude,
  };
  if (!isWeather(result)) throw new Error("Weather data is incomplete.");
  return result;
}
export function weatherLabel(code: number) {
  return code === 0
    ? "Clear skies"
    : code <= 3
      ? "Partly cloudy"
      : code < 51
        ? "Misty"
        : code < 61
          ? "Drizzle"
          : code < 71
            ? "Rain"
            : code < 78
              ? "Snow"
              : code < 85
                ? "Rain showers"
                : code < 90
                  ? "Snow showers"
                  : "Thunderstorms";
}
