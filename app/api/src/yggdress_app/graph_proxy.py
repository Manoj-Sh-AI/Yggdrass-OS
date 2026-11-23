"""Authenticated, read-only transport for the Brain owner's existing graph viewer."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from fastapi import APIRouter, Depends, Response

from .notes_proxy import BrainNotesHTTP, NoRedirect, NotesError

ASSETS = {
    "graph.html": "text/html; charset=utf-8",
    "vis-network.min.js": "text/javascript",
    "three.js": "text/javascript",
    "3d-force-graph.min.js": "text/javascript",
    "inter-latin-400-normal.woff2": "font/woff2",
    "inter-latin-600-normal.woff2": "font/woff2",
}


class BrainGraphHTTP:
    def __init__(self, http):
        self.http = http

    def asset(self, name):
        if name not in ASSETS:
            raise NotesError(404, "Unknown graph asset.", "graph_asset")
        if not self.http.configured:
            raise NotesError(
                503, "The Brain graph connection is not configured.", "graph_unavailable"
            )
        request = Request(
            self.http.root + "/graph/" + name,
            headers={"Authorization": self.http._auth, "Accept": ASSETS[name]},
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=12) as response:
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise NotesError(502, "The graph asset exceeds its size limit.", "graph_asset")
                return raw
        except HTTPError as error:
            raise NotesError(
                503,
                "The Brain graph is unavailable. Check its existing viewer, then retry.",
                "graph_unavailable",
            ) from error
        except (URLError, TimeoutError, OSError):
            raise NotesError(
                503, "The Brain graph service is unavailable. Try again.", "graph_unavailable"
            ) from None

    def status(self):
        try:
            text = self.asset("graph.html").decode("utf-8")
            marker = re.search(r"const\s+DATA\s*=\s*", text)
            if not marker:
                raise ValueError("Missing viewer data")
            data, _ = json.JSONDecoder().raw_decode(text[marker.end() :])
            if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
                raise TypeError("Unsupported viewer data")
            return {
                "nodes": len(data["nodes"]),
                "links": len(data["edges"]),
                "source": "brain-viewer",
            }
        except (ValueError, UnicodeError, AttributeError, TypeError):
            raise NotesError(
                502, "The existing Brain viewer format could not be loaded.", "graph_format"
            ) from None


def graph_router(graph, session):
    router = APIRouter(prefix="/v1/graph")
    authenticated = Depends(session)

    @router.get("/status")
    def status(auth=authenticated):
        from .mobile_policy import mobile_graph, mobile_restricted

        if mobile_restricted(auth):
            text = mobile_graph(graph.asset("graph.html")).decode()
            marker = re.search(r"const\s+DATA\s*=\s*", text)
            data, _ = json.JSONDecoder().raw_decode(text[marker.end() :])
            return {
                "nodes": len(data["nodes"]),
                "links": len(data["edges"]),
                "source": "brain-viewer",
            }
        return graph.status()

    @router.get("/assets/{name}")
    def asset(name: str, auth=authenticated):
        if name not in ASSETS:
            raise NotesError(404, "Unknown graph asset.", "graph_asset")
        from .mobile_policy import mobile_graph, mobile_restricted

        blob = graph.asset(name)
        if name == "graph.html" and mobile_restricted(auth):
            blob = mobile_graph(blob)
        return Response(blob, media_type=ASSETS[name])

    return router


def existing_graph(notes):
    http = notes.http
    # Synthetic Notes fixtures never become an implicit live graph connection.
    if not isinstance(http, BrainNotesHTTP):
        http = BrainNotesHTTP("http://localhost:8100", "", "")
    return BrainGraphHTTP(http)
