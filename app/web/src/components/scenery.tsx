"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useApp } from "./provider";
import {
  fetchWeather,
  isWeather,
  selectScene,
  type Scene,
  type Weather,
} from "@/lib/scenes";
const WEATHER_KEY = "yggdras.weather.v1";
type WeatherContext = {
  weather: Weather | null;
  scene: Scene;
  now: Date;
  status: string;
  refresh: () => void;
};
const Context = createContext<WeatherContext | null>(null);
export function SceneryProvider({ children }: { children: ReactNode }) {
  const { state, ready } = useApp();
  const [now, setNow] = useState(() => new Date("2026-01-01T12:00:00Z")),
    [weather, setWeather] = useState<Weather | null>(null),
    [status, setStatus] = useState("Seasonal scene"),
    [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    setNow(new Date());
    const tick = () => setNow(new Date());
    const t = setInterval(tick, 60000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", tick);
    };
  }, []);
  const { latitude, longitude } = state.preferences.place;
  useEffect(() => {
    if (!ready) return;
    try {
      const w: unknown = JSON.parse(
        localStorage.getItem(WEATHER_KEY) || "null",
      );
      if (
        isWeather(w) &&
        Math.abs(w.latitude - latitude) < 0.05 &&
        Math.abs(w.longitude - longitude) < 0.05
      ) {
        setWeather(w);
      }
    } catch {
      /* Weather cache is optional. */
    }
    const controller = new AbortController();
    let active = true;
    const load = async () => {
      try {
        const w = await fetchWeather(latitude, longitude, controller.signal);
        if (!active) return;
        setWeather(w);
        setStatus("Live weather");
        try {
          localStorage.setItem(WEATHER_KEY, JSON.stringify(w));
        } catch {
          /* In-memory weather still works. */
        }
      } catch {
        if (active) setStatus("Offline · seasonal fallback");
      }
    };
    void load();
    const t = setInterval(load, 1800000);
    const resume = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", resume);
    return () => {
      active = false;
      controller.abort();
      clearInterval(t);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [ready, latitude, longitude, revision]);
  const effectiveWeather =
    weather &&
    now.getTime() - weather.fetchedAt <= 7200000 &&
    Math.abs(weather.latitude - latitude) < 0.05 &&
    Math.abs(weather.longitude - longitude) < 0.05
      ? weather
      : null;
  const scene = selectScene(now, state.preferences, effectiveWeather);
  return (
    <Context.Provider
      value={{ weather: effectiveWeather, scene, now, status, refresh }}
    >
      {children}
    </Context.Provider>
  );
}
export function useScenery() {
  const c = useContext(Context);
  if (!c) throw new Error("Missing SceneryProvider");
  return c;
}
export function SceneBackground() {
  const { scene } = useScenery(),
    { state } = useApp();
  const [loaded, setLoaded] = useState("autumn-sunrise-clear"),
    [previous, setPrevious] = useState<string | null>(null),
    [visible, setVisible] = useState(true),
    [width, setWidth] = useState(1920);
  useEffect(() => {
    const resize = () => setWidth(innerWidth < 768 ? 960 : 1920);
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    let active = true;
    const image = new Image();
    image.onload = () => {
      if (active) {
        setPrevious(loaded);
        setVisible(false);
        setLoaded(scene.key);
        requestAnimationFrame(() =>
          requestAnimationFrame(() => setVisible(true)),
        );
      }
    };
    image.onerror = () => {
      /* Keep the last good scene and the gradient underneath. */
    };
    if (scene.key !== loaded) {
      image.src = `/scenes/${scene.key}-${width}.webp`;
    }
    return () => {
      active = false;
    };
  }, [scene.key, loaded, width]);
  return (
    <div
      className={`scenery ${state.preferences.reducedMotion ? "still" : ""}`}
      aria-hidden="true"
    >
      <div className="scene-fallback" />
      {previous && (
        <div
          className="scene-image"
          style={{
            backgroundImage: `image-set(url('/scenes/${previous}-960.webp') 1x)`,
          }}
        />
      )}
      <div
        className={`scene-image current ${visible ? "visible" : ""}`}
        style={{
          backgroundImage: `url('/scenes/${loaded}-${width}.webp')`,
        }}
      />
      <div className="scene-shade" />
    </div>
  );
}
