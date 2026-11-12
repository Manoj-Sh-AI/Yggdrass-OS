# ruff: noqa: E501  (the inline HTML and CSS template)
"""A tiny read-only web server for Lia's footnote links (127.0.0.1 only, GET only).

    /note/<slug>#cite=<block>   the note, line by line, the cited line highlighted and scrolled to
    /graph/graph.html#select=…  the brain viewer, built once at start into local-data/

Started by `yggdras mcp` on a stable port (YGGDRAS_NOTES_PORT). It never writes to the brain:
there are no write routes, and anything but GET is refused.
"""

from __future__ import annotations

import html
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

HOST = "127.0.0.1"
DEFAULT_PORT = 8765

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
:root {{ --bg: #fbfaf7; --fg: #222; --muted: #777; --hit: #fff1b8; --line: #e4e1da; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1e20; --fg: #e8e6e1; --muted: #9a978f;
  --hit: #5a4a12; --line: #34353a; }} }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.55 system-ui, sans-serif;
  max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.4rem; margin: 0 0 .2rem; }} .meta {{ color: var(--muted); margin-bottom: 1.2rem; }}
.b {{ padding: .35rem .6rem; border-left: 3px solid var(--line); margin: .15rem 0; }}
.field {{ color: var(--muted); font-size: .92rem; }} .history {{ color: var(--muted); }}
.hit {{ background: var(--hit); border-left-color: #c9a227; }}
a {{ color: inherit; }}
</style></head><body>
<h1>{title}</h1>
<div class="meta">{slug} · <a href="/graph/graph.html#select={qslug}&center={qslug}">show in graph</a></div>
{blocks}
<script>
const m = location.hash.match(/cite=(\\d+)/);
if (m) {{ const el = document.getElementById("b" + m[1]);
  if (el) {{ el.classList.add("hit"); el.scrollIntoView({{block: "center"}}); }} }}
</script></body></html>"""


def note_page(slug: str, title: str, blocks: list) -> str:
    rows = "\n".join(
        f'<div class="b {b.kind}" id="b{i}">{html.escape(b.shown)}</div>'
        for i, b in enumerate(blocks)
    )
    return PAGE.format(
        title=html.escape(title), slug=html.escape(slug), qslug=quote(slug), blocks=rows
    )


def make_handler(get_library: Callable, viewer_dir: Path | None, api: Callable | None = None):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, kind: str = "text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 (http.server's name)
            path = unquote(self.path.split("#")[0].split("?")[0])
            if path.startswith("/note/"):
                library = get_library()
                slug = path[len("/note/") :].strip("/")
                if slug not in library.notes:
                    return self._send(404, b"No such note.", "text/plain; charset=utf-8")
                page = note_page(slug, library.notes[slug].name, library.blocks(slug))
                return self._send(200, page.encode("utf-8"))
            if path in ("/graph", "/graph/") and viewer_dir is not None:
                path = "/graph/graph.html"
            if path.startswith("/api/") and api is not None:  # the app's reads (D44 §6)
                return self._api(path[len("/api/") :].strip("/"))
            if path.startswith("/graph/") and viewer_dir is not None:
                name = path[len("/graph/") :]
                target = (viewer_dir / name).resolve()
                if viewer_dir.resolve() in target.parents and target.is_file():
                    kind = {
                        ".html": "text/html; charset=utf-8",
                        ".js": "text/javascript",
                        ".woff2": "font/woff2",
                    }.get(target.suffix, "application/octet-stream")
                    return self._send(200, target.read_bytes(), kind)
            return self._send(404, b"Not found.", "text/plain; charset=utf-8")

        def _api(self, route: str):
            import json

            name, _, slug = route.partition("/")
            calls = {"tree": ("note_tree",), "note": ("note_with_relationships", slug),
                     "version": ("version", slug)}  # fmt: skip
            if name not in calls or (name != "tree" and not slug):
                return self._send(404, b"Not found.", "text/plain; charset=utf-8")
            data = api(*calls[name])
            if data is None:
                return self._send(404, b"No such note.", "text/plain; charset=utf-8")
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            return self._send(200, body, "application/json; charset=utf-8")

        def _refuse(self):
            self._send(405, b"Read-only.", "text/plain; charset=utf-8")

        do_POST = do_PUT = do_DELETE = do_PATCH = _refuse  # noqa: N815

        def log_message(self, *args):  # stdout and stderr belong to MCP; stay quiet
            pass

    return Handler


def start(get_library: Callable, port: int = DEFAULT_PORT, viewer_dir: Path | None = None,
          api: Callable | None = None):  # fmt: skip
    """Start serving on 127.0.0.1:*port* in a daemon thread. Returns the server, or None if the
    port is taken (Lia then falls back to plain footnotes)."""
    try:
        server = ThreadingHTTPServer((HOST, port), make_handler(get_library, viewer_dir, api))
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_viewer(root: Path, out_dir: Path) -> Path | None:
    """The brain viewer, built once from the brain's current files into *out_dir*."""
    from yggdras.data.graph import structural, viewer

    try:
        return viewer.render(structural.build_map(root, structural.mapped_shelves()), root, out_dir)
    except Exception:  # the viewer is a nicety; footnote pages work without it
        return None
