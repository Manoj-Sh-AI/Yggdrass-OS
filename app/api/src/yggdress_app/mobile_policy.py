"""Device-session restrictions. No Brain storage access or semantic processing."""

import json
import re

from .notes_proxy import NotesError

PREFIX = "mobile:v1:"


def is_mobile(auth):
    return str((auth or {}).get("csrf", "")).startswith(PREFIX)


def mobile_restricted(auth):
    # Only server configuration can grant the owner's full catalogue. Session
    # identity remains mobile for CSRF, bearer and legacy-route restrictions.
    return is_mobile(auth) and (auth or {}).get("mobile_sensitive_access") is not True


def sensitive(note):
    if note.get("sensitive") is True or str(note.get("sensitivity", "")).lower() == "high":
        return True
    text = note.get("rawBody", note.get("body", ""))
    if not isinstance(text, str):
        return True  # Unknown content must not become an implicit phone export.
    if text.startswith("---"):
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
        if not match:
            return True
        return bool(re.search(r"(?im)^\s*sensitivity\s*:\s*['\"]?high['\"]?\s*(?:#.*)?$", match[1]))
    return False


def require_mobile_safe(note, auth):
    if mobile_restricted(auth) and sensitive(note):
        raise NotesError(403, "This note is excluded from mobile access.", "sensitive_note")


def mobile_graph(blob):
    """Keep the Brain owner's viewer, excluding sensitive nodes before transmission."""
    try:
        text = blob.decode("utf-8")
        marker = re.search(r"const\s+DATA\s*=\s*", text)
        if not marker:
            raise ValueError
        data, length = json.JSONDecoder().raw_decode(text[marker.end() :])
        nodes = [n for n in data["nodes"] if n.get("sensitive") is False]
        identifiers = {n["id"] for n in nodes}
        edges = [e for e in data["edges"] if e["from"] in identifiers and e["to"] in identifiers]
        degree = {identifier: 0 for identifier in identifiers}
        for edge in edges:
            degree[edge["from"]] += 1
            degree[edge["to"]] += 1
        safe = {
            "schema": data.get("schema"),
            "nodes": [{**n, "degree": degree[n["id"]]} for n in nodes],
            "edges": edges,
        }
        encoded = json.dumps(safe, ensure_ascii=False).replace("<", "\\u003c")
        return (text[: marker.end()] + encoded + text[marker.end() + length :]).encode()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise NotesError(
            502, "The graph cannot be safely prepared for this phone.", "graph_format"
        ) from None
