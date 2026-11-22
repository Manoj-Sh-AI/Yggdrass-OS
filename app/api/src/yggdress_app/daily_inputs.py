"""Opt-in public inputs. Only the location goes to a weather provider; feeds get no user data."""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from psycopg.types.json import Jsonb

SOURCES = {
    "openai": {"name": "OpenAI", "url": "https://openai.com/news/rss.xml"},
    "deepmind": {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml"},
    "huggingface": {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
    "nvidia": {"name": "NVIDIA", "url": "https://blogs.nvidia.com/feed/"},
}
SOURCE_HOSTS = {
    "openai": {"openai.com"},
    "deepmind": {"deepmind.google", "blog.google"},
    "huggingface": {"huggingface.co"},
    "nvidia": {"blogs.nvidia.com", "www.nvidia.com"},
}


def fetch(url, limit=5_500_000):
    # Hosts and paths for requests are fixed below or validated against the publisher.
    with httpx.stream(
        "GET",
        url,
        timeout=5,
        follow_redirects=False,
        headers={"User-Agent": "Yggdras/1.0 (personal daily brief)"},
    ) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                raise ValueError("Public source exceeds size limit.")
        return bytes(body)


def _umbrella(hours):
    # ASSUMPTION: personal morning umbrella rule for the 07:00–20:00 local window.
    complete = []
    for stamp, p, mm, storm in hours:
        if not 7 <= stamp.hour < 20 or mm is None or not math.isfinite(mm) or mm < 0:
            continue
        if p is not None and (not math.isfinite(p) or not 0 <= p <= 100):
            continue
        complete.append((stamp, p, mm, storm))
        if storm or (p is not None and (p >= 50 or (p >= 30 and mm >= 0.3))):
            reason = (
                "thunderstorms forecast" if storm else f"{p:.0f}% precipitation chance, {mm:.1f} mm"
            )
            return f"Bring an umbrella: {reason} around {stamp:%H:%M}."
    total = sum(hour[2] for hour in complete)
    if total >= 1:
        return f"Bring an umbrella: {total:.1f} mm precipitation forecast during the day."
    if len({hour[0].hour for hour in complete}) < 13 or any(h[1] is None for h in complete):
        raise ValueError("Incomplete daytime forecast.")
    return f"Umbrella optional: {total:.1f} mm precipitation forecast during the day."


def weather(settings, day, zone, get=fetch):
    lat, lon = settings["latitude"], settings["longitude"]
    if lat is None or lon is None:
        return None
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": zone,
        "start_date": day,
        "end_date": day,
        "hourly": "precipitation_probability,precipitation,weather_code",
    }
    try:
        raw = json.loads(get("https://api.open-meteo.com/v1/dwd-icon?" + urlencode(params)))[
            "hourly"
        ]
        hours = [
            (datetime.fromisoformat(t), p, n, c in (95, 96, 97, 99))
            for t, p, n, c in zip(
                raw["time"],
                raw["precipitation_probability"],
                raw["precipitation"],
                raw["weather_code"],
                strict=True,
            )
            if t.startswith(day.isoformat())
        ]
        return {
            "text": _umbrella(hours),
            "source": "DWD via Open-Meteo (CC BY 4.0)",
            "url": "https://open-meteo.com/en/docs/dwd-api",
            "license": "https://creativecommons.org/licenses/by/4.0/",
        }
    except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError):
        params = {
            "lat": lat,
            "lon": lon,
            "tz": zone,
            "date": day.isoformat(),
            "last_date": (day + timedelta(days=1)).isoformat(),
        }
        raw = json.loads(get("https://api.brightsky.dev/weather?" + urlencode(params)))
        hours = []
        for rec in raw["weather"]:
            stamp = datetime.fromisoformat(rec["timestamp"]).astimezone(ZoneInfo(zone))
            if stamp.date() == day:
                hours.append(
                    (
                        stamp,
                        rec.get("precipitation_probability"),
                        rec.get("precipitation"),
                        rec.get("condition") == "thunderstorm",
                    )
                )
        return {
            "text": _umbrella(hours),
            "source": "Deutscher Wetterdienst via Bright Sky",
            "url": "https://brightsky.dev/",
        }


def _strip(text):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", text or "")).split())


def _items(source, raw, now):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unexpected feed document.")
    root = ET.fromstring(raw)
    if root.tag != "rss":
        raise ValueError("Expected RSS.")
    newest = None
    recent = []
    for node in root.iterfind("channel/item"):
        try:
            published = parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(UTC)
            parsed = urlsplit((node.findtext("link") or "").strip())
            if (
                parsed.scheme != "https"
                or parsed.hostname not in SOURCE_HOSTS[source]
                or parsed.port
                or parsed.username
                or parsed.password
            ):
                continue
        except (ValueError, TypeError):
            continue
        newest = max(published, newest) if newest else published
        if now - timedelta(hours=36) <= published <= now:
            title = _strip(node.findtext("title"))[:250]
            if title:
                recent.append(
                    {
                        "title": title,
                        "snippet": _strip(node.findtext("description"))[:350],
                        "url": urlunsplit(("https", parsed.hostname, parsed.path, "", "")),
                        "source": SOURCES[source]["name"],
                        "source_id": source,
                        "published": published.isoformat(),
                    }
                )
    return recent, ("stale" if not newest or now - newest > timedelta(days=14) else "ready")


class Article(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.paragraph = []
        self.parts = []
        self.tag = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "title", "p"):
            self.tag = tag
            self.parts = []

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.tag:
            segment = " ".join(" ".join(self.parts).split())
            (self.paragraph if tag == "p" else self.title).append(segment)
            self.tag = ""


def _digest_news(settings, now, seen, get):
    pool = {}
    status = {}
    for key in dict.fromkeys(settings["approved_feeds"]):
        if key not in SOURCES:
            continue
        try:
            items, status[key] = _items(key, get(SOURCES[key]["url"]), now)
            for item in items:
                if item["url"] not in seen:
                    pool.setdefault(item["url"], item)
        except (ValueError, TypeError, ET.ParseError, httpx.HTTPError, OSError):
            status[key] = "unavailable"
    # ASSUMPTION: deterministic AI/hardware relevance when no paid ranking model is connected.
    words = re.compile(
        r"\b(ai|inference|model|chip|gpu|agent|hardware|robot|training|software|quantization)\b",
        re.IGNORECASE,
    )
    ranked = sorted(
        pool.values(),
        key=lambda i: (len(words.findall(i["title"] + " " + i["snippet"])), i["published"]),
        reverse=True,
    )
    verified = []
    for item in ranked[:8]:
        try:
            article = Article()
            article.feed(get(item["url"]).decode("utf-8", "replace"))
            if not any(item["title"].casefold() in title.casefold() for title in article.title):
                continue
            span = next(
                (p for p in article.paragraph if len(p.split()) >= 8 and words.search(p)), ""
            )
            if not span:
                continue
            item = {k: v for k, v in item.items() if k != "snippet"}
            item.update(tag="primary-verified", quote=" ".join(span.split()[:20]))
            verified.append(item)
            if len(verified) == 5:
                break
        except (ValueError, httpx.HTTPError, OSError):
            continue
    return verified, status


def settings_hash(settings):
    keys = [settings.get(k) for k in ("enabled", "latitude", "longitude", "city", "approved_feeds")]
    return hashlib.sha256(json.dumps(keys, sort_keys=True, default=str).encode()).hexdigest()


def read_cached(db, day, zone):
    settings = db.execute("SELECT * FROM app.daily_routine_settings LIMIT 1").fetchone()
    if not settings or not settings["enabled"]:
        return {}
    return (
        db.execute(
            "SELECT weather,news,status FROM app.daily_inputs "
            "WHERE for_date=%s AND timezone=%s AND settings_hash=%s",
            (day, zone, settings_hash(settings)),
        ).fetchone()
        or {}
    )


def refresh(database, day, zone, *, get=fetch, now=None):
    now = now or datetime.now(UTC)
    with database.connect() as db:
        settings = db.execute("SELECT * FROM app.daily_routine_settings LIMIT 1").fetchone()
        if not settings or not settings["enabled"]:
            return {}
        signature = settings_hash(settings)
        cached = read_cached(db, day, zone)
        if cached:
            return cached
        prior = db.execute(
            "SELECT news FROM app.daily_inputs WHERE for_date>=%s AND for_date<%s",
            (day - timedelta(days=14), day),
        ).fetchall()
    seen = {item["url"] for row in prior for item in row["news"]}
    news, status = _digest_news(settings, now, seen, get)
    try:
        forecast = weather(settings, day, zone, get)
        status["weather"] = "ready" if forecast else "no_location"
    except (ValueError, KeyError, TypeError, httpx.HTTPError, OSError):
        forecast = None
        status["weather"] = "unavailable"
    with database.connect() as db:
        current = db.execute(
            "SELECT * FROM app.daily_routine_settings LIMIT 1 FOR SHARE"
        ).fetchone()
        if not current or settings_hash(current) != signature:
            return {}
        return db.execute(
            "INSERT INTO app.daily_inputs(for_date,timezone,settings_hash,weather,news,status) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(for_date,timezone) DO UPDATE SET "
            "settings_hash=excluded.settings_hash,weather=excluded.weather,news=excluded.news,status=excluded.status,"
            "updated_at=now() RETURNING weather,news,status",
            (
                day,
                zone,
                signature,
                Jsonb(forecast) if forecast else None,
                Jsonb(news),
                Jsonb(status),
            ),
        ).fetchone()
