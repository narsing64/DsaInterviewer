"""HTTP server (stdlib only). Run:  python -m voice_dsa.server"""
import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import db, supervisor
from .llm import transcribe

STATIC = Path(__file__).parent / "static"
PORT = int(os.environ.get("PORT", 8001))
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")  # if set, every /api call must send it
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"  # hosting platforms set PORT


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        if ACCESS_CODE and self.headers.get("X-Access-Code") != ACCESS_CODE:
            self._send(401, {"error": "access code required"})
            return False
        return True

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/") and not self._authorized():
            return
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/topics":
            return self._send(200, supervisor.topics())
        if path == "/api/history":
            return self._send(200, {"stats": db.stats(), "sessions": db.history()})
        if path.startswith("/api/session/"):
            s = db.get_session(path.rsplit("/", 1)[1])
            return self._send(200 if s else 404, s or {"error": "not found"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/start":
                return self._send(200, supervisor.start(req.get("topic") or None, req.get("difficulty") or None))
            if self.path == "/api/turn":
                text = req.get("text", "")
                if req.get("audio"):
                    text = transcribe(base64.b64decode(req["audio"]), req.get("mime", "audio/webm"))
                    if not text and not req.get("code"):
                        return self._send(200, {"transcript": "", "reply": ""})
                out = supervisor.turn(req["session_id"], text, req.get("code", ""), bool(req.get("end")))
                return self._send(200, {"transcript": text, **out})
            if self.path == "/api/voice":
                supervisor.SESSIONS[req["session_id"]]["voice"] = req["voice"]
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})
        except Exception as e:
            print("error:", repr(e), file=sys.stderr)
            self._send(500, {"error": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    db.init_db()
    print(f"Voice DSA Interviewer running at http://localhost:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
