"use client";
import { useEffect, useRef, useState } from "react";
import type { DayPhase, Place, Preferences, Season, Sky } from "@/lib/types";
import { phases, sceneKeys, seasons, skies, weatherLabel } from "@/lib/scenes";
import { useApp } from "./provider";
import { useScenery } from "./scenery";
import { Icon, Modal, Panel } from "./ui";
type CityResult = {
  id: number;
  name: string;
  country: string;
  admin1?: string;
  latitude: number;
  longitude: number;
  timezone: string;
};
export function SettingsPage() {
  const { state, update, reset, toast } = useApp(),
    { weather, scene, status, refresh } = useScenery();
  const prefs = state.preferences;
  const [name, setName] = useState(prefs.name),
    [query, setQuery] = useState(""),
    [cities, setCities] = useState<CityResult[]>([]),
    [searchStatus, setSearchStatus] = useState(""),
    [locating, setLocating] = useState(false),
    [resetOpen, setResetOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [previewSeason, setPreviewSeason] = useState<Season>("autumn");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => setName(prefs.name), [prefs.name]);
  async function change(partial: Partial<Preferences>) {
    const ok = await update((s) => ({
      ...s,
      preferences: { ...s.preferences, ...partial },
    }));
    if (ok) toast("Preferences saved.");
  }
  useEffect(() => {
    controller.current?.abort();
    if (query.trim().length < 2) {
      setCities([]);
      setSearchStatus("");
      return;
    }
    const abort = new AbortController();
    controller.current = abort;
    const t = setTimeout(async () => {
      setSearchStatus("Finding cities…");
      try {
        const response = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query.trim())}&count=5&language=en&format=json`,
          { signal: abort.signal },
        );
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (!abort.signal.aborted) {
          const results: CityResult[] = data.results || [];
          setCities(results);
          setSearchStatus(
            results.length ? "" : "No cities found. Try a nearby city.",
          );
        }
      } catch {
        if (!abort.signal.aborted)
          setSearchStatus(
            "City search is offline. Your current location is unchanged.",
          );
      }
    }, 300);
    return () => {
      clearTimeout(t);
      abort.abort();
    };
  }, [query]);
  async function choose(place: Place) {
    await change({ place, locationPrompted: true });
    setQuery("");
    setCities([]);
  }
  function locate() {
    if (!navigator.geolocation) {
      toast("This browser cannot provide location. Search for a city instead.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating(false);
        void choose({
          name: "Your location",
          latitude: p.coords.latitude,
          longitude: p.coords.longitude,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        });
      },
      () => {
        setLocating(false);
        setSearchStatus(
          "Location access was unavailable. Search for a city below.",
        );
      },
      { timeout: 12000, maximumAge: 1800000 },
    );
  }
  const allAuto =
    prefs.season === "auto" && prefs.phase === "auto" && prefs.sky === "auto";
  return (
    <div className="standard-page settings-page">
      <div className="page-intro">
        <div>
          <h1>Settings</h1>
        </div>
      </div>
      <div className="settings-layout">
        <div className="settings-main">
          <Panel title="Your profile">
            <form
              className="profile-form"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                await change({ name: name.trim() || "Alex" });
                setBusy(false);
              }}
            >
              <div className="avatar large">{prefs.name.slice(0, 1)}</div>
              <label>
                Display name
                <input
                  value={name}
                  maxLength={40}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <button className="button" disabled={busy || !name.trim()}>
                {busy ? "Saving…" : "Save profile"}
              </button>
            </form>
            <p className="settings-footnote">
              Single-owner password sign-in · display preferences stay in this
              browser
            </p>
          </Panel>
          <Panel
            title="Appearance"
            action={
              <span className="live-badge">
                <span />
                {allAuto ? "Automatic" : "Custom scene"}
              </span>
            }
          >
            <div
              className="current-scene"
              style={{
                backgroundImage: `linear-gradient(0deg,rgba(5,13,25,.8),transparent),url('/scenes/${scene.key}-960.webp')`,
              }}
            >
              <div>
                <span>YOUR CURRENT VIEW</span>
                <strong>
                  {scene.season} · {scene.phase} · {scene.sky}
                </strong>
                <small>{status}</small>
              </div>
              <Icon name={scene.phase === "night" ? "Moon" : "Sun"} size={25} />
            </div>
            <div className="form-row scene-selects">
              <label>
                Season
                <select
                  aria-label="Season"
                  value={prefs.season}
                  onChange={(e) =>
                    void change({ season: e.target.value as Season | "auto" })
                  }
                >
                  <option value="auto">Follow the seasons</option>
                  {seasons.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Time of day
                <select
                  aria-label="Time of day"
                  value={prefs.phase}
                  onChange={(e) =>
                    void change({ phase: e.target.value as DayPhase | "auto" })
                  }
                >
                  <option value="auto">Follow the sun</option>
                  {phases.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label>
                Weather
                <select
                  aria-label="Weather"
                  value={prefs.sky}
                  onChange={(e) =>
                    void change({ sky: e.target.value as Sky | "auto" })
                  }
                >
                  <option value="auto">Follow the weather</option>
                  {skies.map((w) => (
                    <option key={w}>{w}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="settings-line">
              <div>
                <strong>Let nature choose</strong>
                <p>Use your location, season, and local light automatically.</p>
              </div>
              <button
                className="button small-button"
                disabled={allAuto}
                onClick={() =>
                  void change({ season: "auto", phase: "auto", sky: "auto" })
                }
              >
                Restore automatic
              </button>
            </div>
            <details className="quiet-disclosure">
              <summary>Preview landscapes</summary>
              <div className="scene-library-heading">
                <h3>Landscapes</h3>
                <select
                  aria-label="Preview season"
                  value={previewSeason}
                  onChange={(e) => setPreviewSeason(e.target.value as Season)}
                >
                  {seasons.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="scene-library">
                {sceneKeys
                  .filter((key) => key.startsWith(previewSeason))
                  .map((key) => (
                    <button
                      className={scene.key === key ? "selected" : ""}
                      aria-label={`Use ${key.replaceAll("-", " ")} scene`}
                      aria-pressed={scene.key === key}
                      key={key}
                      onClick={() => {
                        const [season, phase, sky] = key.split("-");
                        void change({
                          season: season as Season,
                          phase: phase as DayPhase,
                          sky: sky as Sky,
                        });
                      }}
                    >
                      <img
                        src={`/scenes/${key}-480.webp`}
                        alt={`${key.replaceAll("-", " ")} alpine lake`}
                        loading="lazy"
                      />
                      <span>{key.split("-").slice(1).join(" · ")}</span>
                      {scene.key === key && (
                        <Icon name="CircleCheck" size={18} />
                      )}
                    </button>
                  ))}
              </div>
            </details>
            <div className="settings-line">
              <div>
                <strong>Reduce transparency</strong>
                <p>
                  Use solid surfaces with less blur for a quieter reading
                  experience.
                </p>
              </div>
              <button
                role="switch"
                aria-checked={!!prefs.reducedTransparency}
                aria-label="Reduce transparency"
                className={`switch ${prefs.reducedTransparency ? "on" : ""}`}
                onClick={() =>
                  void change({
                    reducedTransparency: !prefs.reducedTransparency,
                  })
                }
              >
                <span />
              </button>
            </div>
            <div className="settings-line">
              <div>
                <strong>Quiet transitions</strong>
                <p>Keep the scenery still and minimize interface animation.</p>
              </div>
              <button
                role="switch"
                aria-checked={prefs.reducedMotion}
                aria-label="Quiet transitions"
                className={`switch ${prefs.reducedMotion ? "on" : ""}`}
                onClick={() =>
                  void change({ reducedMotion: !prefs.reducedMotion })
                }
              >
                <span />
              </button>
            </div>
          </Panel>
        </div>
        <div className="settings-side">
          <Panel title="Location">
            <div className="location-card">
              <span className="location-icon">
                <Icon name="MapPin" size={26} />
              </span>
              <h3>{prefs.place.name}</h3>
              <p>
                {weather &&
                Math.abs(weather.latitude - prefs.place.latitude) < 0.05
                  ? `${Math.round(weather.temperature)}°C · ${weatherLabel(weather.code)}`
                  : "Seasonal scenery is ready"}
              </p>
              <small>{weather?.timezone || prefs.place.timezone}</small>
              <button className="button" disabled={locating} onClick={locate}>
                <Icon name="LocateFixed" size={16} />
                {locating ? "Finding you…" : "Use my location"}
              </button>
            </div>
            <label className="city-search-label">
              Or choose a city
              <div className="filter-input">
                <Icon name="Search" size={16} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search for a city…"
                  aria-label="Search cities"
                />
              </div>
            </label>
            <p role="status" className="settings-footnote">
              {searchStatus}
            </p>
            <div className="city-results">
              {cities.map((c) => (
                <button
                  key={c.id}
                  onClick={() =>
                    void choose({
                      name: c.name,
                      latitude: c.latitude,
                      longitude: c.longitude,
                      timezone: c.timezone || "UTC",
                    })
                  }
                >
                  <span>
                    <strong>{c.name}</strong>
                    <small>
                      {[c.admin1, c.country].filter(Boolean).join(", ")}
                    </small>
                  </span>
                  <Icon name="ArrowRight" size={15} />
                </button>
              ))}
            </div>
            <button
              className="text-link refresh-weather"
              onClick={() => {
                refresh();
                toast("Refreshing your local weather…");
              }}
            >
              <Icon name="RefreshCw" size={13} />
              Refresh weather
            </button>
            <p className="settings-footnote">
              Location is used only for scenery and weather. Notes use the Brain
              service; tasks and calendar use the application database. Weather
              by{" "}
              <a
                href="https://open-meteo.com/"
                target="_blank"
                rel="noreferrer"
              >
                Open-Meteo
              </a>
              .
            </p>
          </Panel>
          <Panel title="Reset appearance">
            <p className="settings-description">
              Restore this browser’s appearance and location preferences.
            </p>
            <button
              className="button reset-button"
              onClick={() => setResetOpen(true)}
            >
              <Icon name="RotateCcw" size={16} />
              Reset appearance
            </button>
            <p className="settings-footnote">
              Notes, tasks and routines are preserved.
            </p>
          </Panel>
        </div>
      </div>
      <Modal
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset appearance?"
        description="Restore appearance and location preferences for this browser."
      >
        <p>Notes, tasks and routine execution are preserved.</p>
        <div className="modal-actions">
          <button className="button" onClick={() => setResetOpen(false)}>
            Keep preferences
          </button>
          <button
            className="button primary"
            onClick={async () => {
              await reset();
              setResetOpen(false);
            }}
          >
            Reset appearance
          </button>
        </div>
      </Modal>
    </div>
  );
}
