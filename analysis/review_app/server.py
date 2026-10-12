"""Review app server for Cartwheel error analysis (HW4).

Standard-library HTTP server. Serves the single-file UI and a file-backed API
over analysis/state/. Adapted from analysis/server.py: same endpoint contract so
the state files stay compatible with analysis/helpers and the Module 3 tooling,
but the sample payload is session-grouped and carries the scenario answer key.

Run:  uv run python analysis/review_app/server.py [--port 8020]
"""
from __future__ import annotations
import argparse, json, pathlib, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
UI = pathlib.Path(__file__).resolve().parent / "ui" / "index.html"

FILES = {
    "samples": STATE / "samples.json",
    "annotations": STATE / "annotations.json",
    "patterns": STATE / "patterns.json",
    "suggestions": STATE / "suggestions.json",
    "graph": STATE / "graph.json",
    "labels": STATE / "labels_draft.json",
    "hw5_candidates": STATE / "hw5_candidates.json",
    "hw5_labels": STATE / "hw5_labels.json",
}
DEFAULTS = {
    "samples": {"samples": []},
    "annotations": {"annotations": []},
    "patterns": {"modes": []},
    "suggestions": [],
    "graph": {"nodes": []},
    "labels": {},
    "hw5_candidates": {"candidates": []},
    "hw5_labels": {},
}

def read(name):
    p = FILES[name]
    if not p.exists():
        return DEFAULTS[name]
    try:
        return json.loads(p.read_text() or "null") or DEFAULTS[name]
    except json.JSONDecodeError:
        return DEFAULTS[name]

def write(name, payload):
    p = FILES[name]
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.stat().st_size > 2:
        shutil.copyfile(p, p.with_suffix(p.suffix + ".bak"))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(p)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/" not in (args[0] if args else ""):
            return
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/hw5":
            f = UI.parent / "hw5.html"
            if not f.exists():
                return self._send(500, {"error": f"missing {f}"})
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
        if path in ("/", "/index.html"):
            if not UI.exists():
                return self._send(500, {"error": f"UI missing at {UI}"})
            return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/api/"):
            name = path[5:]
            if name in FILES:
                return self._send(200, read(name))
        self._send(404, {"error": "not found", "path": path})

    def do_POST(self):
        path = self.path.split("?")[0]
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        name = path[5:]
        if name not in FILES or name in ("graph", "hw5_candidates"):
            return self._send(404, {"error": f"cannot write {name}"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"null")
        except Exception as exc:
            return self._send(400, {"error": f"bad json: {exc}"})
        if payload is None:
            return self._send(400, {"error": "empty payload"})
        write(name, payload)
        self._send(200, {"ok": True, "saved": name})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8020)
    args = ap.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    for name in ("annotations", "patterns", "suggestions"):
        if not FILES[name].exists():
            write(name, DEFAULTS[name])
    s = read("samples").get("samples", [])
    print(f"review app on http://localhost:{args.port}  ({len(s)} sessions loaded)")
    print(f"state dir: {STATE}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()

if __name__ == "__main__":
    main()
