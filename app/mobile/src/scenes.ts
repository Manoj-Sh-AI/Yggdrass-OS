import type { ImageSourcePropType } from "react-native";

/** Same scene set and clock fallback as the web app (web/src/lib/scenes.ts). */
export type Season = "spring" | "summer" | "autumn" | "winter";
export type DayPhase = "sunrise" | "afternoon" | "night";
export type Sky = "clear" | "rainy";
export type SceneKey = `${Season}-${DayPhase}-${Sky}`;

const seasons: Season[] = ["spring", "summer", "autumn", "winter"];

export function seasonFor(month: number, latitude = 1): Season {
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

export function phaseFor(minutes: number): DayPhase {
  return minutes >= 360 && minutes < 540
    ? "sunrise"
    : minutes >= 540 && minutes < 1080
      ? "afternoon"
      : "night";
}

/** Device clock only: the phone has no weather feed, so the sky stays clear. */
export function sceneKey(now: Date, sky: Sky = "clear"): SceneKey {
  const minutes = now.getHours() * 60 + now.getMinutes();
  return `${seasonFor(now.getMonth())}-${phaseFor(minutes)}-${sky}`;
}

export const sceneImages: Record<SceneKey, ImageSourcePropType> = {
  "spring-sunrise-clear": require("../assets/scenes/spring-sunrise-clear-960.webp"),
  "spring-sunrise-rainy": require("../assets/scenes/spring-sunrise-rainy-960.webp"),
  "spring-afternoon-clear": require("../assets/scenes/spring-afternoon-clear-960.webp"),
  "spring-afternoon-rainy": require("../assets/scenes/spring-afternoon-rainy-960.webp"),
  "spring-night-clear": require("../assets/scenes/spring-night-clear-960.webp"),
  "spring-night-rainy": require("../assets/scenes/spring-night-rainy-960.webp"),
  "summer-sunrise-clear": require("../assets/scenes/summer-sunrise-clear-960.webp"),
  "summer-sunrise-rainy": require("../assets/scenes/summer-sunrise-rainy-960.webp"),
  "summer-afternoon-clear": require("../assets/scenes/summer-afternoon-clear-960.webp"),
  "summer-afternoon-rainy": require("../assets/scenes/summer-afternoon-rainy-960.webp"),
  "summer-night-clear": require("../assets/scenes/summer-night-clear-960.webp"),
  "summer-night-rainy": require("../assets/scenes/summer-night-rainy-960.webp"),
  "autumn-sunrise-clear": require("../assets/scenes/autumn-sunrise-clear-960.webp"),
  "autumn-sunrise-rainy": require("../assets/scenes/autumn-sunrise-rainy-960.webp"),
  "autumn-afternoon-clear": require("../assets/scenes/autumn-afternoon-clear-960.webp"),
  "autumn-afternoon-rainy": require("../assets/scenes/autumn-afternoon-rainy-960.webp"),
  "autumn-night-clear": require("../assets/scenes/autumn-night-clear-960.webp"),
  "autumn-night-rainy": require("../assets/scenes/autumn-night-rainy-960.webp"),
  "winter-sunrise-clear": require("../assets/scenes/winter-sunrise-clear-960.webp"),
  "winter-sunrise-rainy": require("../assets/scenes/winter-sunrise-rainy-960.webp"),
  "winter-afternoon-clear": require("../assets/scenes/winter-afternoon-clear-960.webp"),
  "winter-afternoon-rainy": require("../assets/scenes/winter-afternoon-rainy-960.webp"),
  "winter-night-clear": require("../assets/scenes/winter-night-clear-960.webp"),
  "winter-night-rainy": require("../assets/scenes/winter-night-rainy-960.webp"),
};
