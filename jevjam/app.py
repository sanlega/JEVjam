"""App local de JEVjam: opciones, botón rojo y la jam en directo en el navegador.

    python -m jevjam.app            # abre http://127.0.0.1:8765
    python -m jevjam.app --port 9000 --no-browser

Solo escucha en 127.0.0.1: el micro, el MIDI y la clave de Jev se quedan en tu máquina.
Servidor de la biblioteca estándar; la página recibe los compases por Server-Sent Events.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import queue
import threading
import webbrowser
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .brain import load_dotenv
from .session import Session, SessionConfig, list_devices

WEB = Path(__file__).parent / "web"
RECORDINGS = Path("recordings")


class Hub:
    """Una sesión a la vez; reparte sus eventos a todas las pestañas abiertas."""

    def __init__(self):
        self.session: Session | None = None
        self.thread: threading.Thread | None = None
        self.history: list[tuple[str, dict]] = []  # eventos de la sesión en curso (para pestañas nuevas)
        self.subscribers: list[queue.Queue] = []
        self.lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def emit(self, kind: str, data: dict) -> None:
        with self.lock:
            self.history = (self.history + [(kind, data)])[-400:]
            for q in list(self.subscribers):
                q.put((kind, data))

    def start(self, cfg: SessionConfig) -> None:
        with self.lock:
            if self.running:
                raise RuntimeError("ya hay una jam en marcha")
            self.history = []
        self.session = Session(cfg, emit=self.emit)

        def run():
            try:
                self.session.run()
            except Exception as exc:  # p. ej. falta la clave de Jev
                self.emit("status", {"state": "error", "text": str(exc)})

        self.thread = threading.Thread(target=run, daemon=True, name="jam")
        self.thread.start()

    def stop(self) -> None:
        if self.session:
            self.session.stop()


HUB = Hub()


def parse_config(body: dict) -> SessionConfig:
    allowed = {f.name for f in fields(SessionConfig)}
    unknown = set(body) - allowed
    if unknown:
        raise ValueError(f"opciones desconocidas: {', '.join(sorted(unknown))}")
    cfg = SessionConfig(**body)
    # JSON → tipos de la configuración
    cfg.bpm = float(cfg.bpm) if cfg.bpm not in (None, "") else None
    cfg.demo_bpm = float(cfg.demo_bpm)
    cfg.bars = int(cfg.bars) if cfg.bars not in (None, "") else None
    cfg.channel = int(cfg.channel or 0)
    cfg.key = cfg.key or None
    cfg.device = str(cfg.device) if cfg.device not in (None, "") else None
    for name in ("bpm", "demo_bpm"):
        v = getattr(cfg, name)
        if v is not None and not 40 <= float(v) <= 240:
            raise ValueError(f"{name} debe estar entre 40 y 240")
    if cfg.bars is not None and int(cfg.bars) < 1:
        raise ValueError("bars debe ser ≥ 1")
    if cfg.input not in ("mic", "demo") and not Path(cfg.input).is_file():
        raise ValueError(f"no existe el archivo {cfg.input}")
    cfg.fixed_key()  # valida la tonalidad
    return cfg


def recent_sessions(limit: int = 12) -> list[dict]:
    out = []
    for folder in sorted(RECORDINGS.glob("session-*/"), reverse=True)[:limit]:
        meta = {}
        with contextlib.suppress(Exception):
            meta = json.loads((folder / "meta.json").read_text())
        out.append({"folder": str(folder), "started": meta.get("started"),
                    "bars": meta.get("stats", {}).get("bars"),
                    "seconds": round(meta.get("input_seconds", 0)),
                    "input": (meta.get("argv") or {}).get("input"),
                    "has_audio": (folder / "input.wav").exists()})
    return out


def review_text(folder: str) -> str:
    path = Path(folder).resolve()
    if RECORDINGS.resolve() not in path.parents or not (path / "bars.jsonl").exists():
        raise ValueError("carpeta de sesión no válida")
    from .review import main as review_main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        review_main([str(path)])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "JEVjam"

    def log_message(self, *args) -> None:  # sin ruido en la terminal
        pass

    # ------------------------------------------------------------ utilidades
    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _same_origin(self) -> bool:
        """Evita que otra web abierta en el navegador arranque la jam (CSRF a localhost)."""
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc == self.headers.get("Host")

    # ----------------------------------------------------------------- rutas
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            body = (WEB / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/options":
            import os

            load_dotenv()
            try:
                devices = list_devices()
            except Exception as exc:
                devices = {"inputs": [], "midi_outputs": [], "error": str(exc)}
            self._json({**devices, "api_key": bool(os.environ.get("TYPESAFE_API_KEY")),
                        "running": HUB.running, "sessions": recent_sessions()})
        elif url.path == "/api/sessions":
            self._json(recent_sessions())
        elif url.path == "/api/review":
            try:
                self._json({"text": review_text(parse_qs(url.query).get("folder", [""])[0])})
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
        elif url.path == "/api/events":
            self._events()
        else:
            self._json({"error": "no encontrado"}, 404)

    def do_POST(self) -> None:
        if not self._same_origin():
            return self._json({"error": "origen no permitido"}, 403)
        url = urlparse(self.path)
        if url.path == "/api/start":
            try:
                HUB.start(parse_config(self._body()))
                self._json({"ok": True})
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, 400)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, 409)
        elif url.path == "/api/stop":
            HUB.stop()
            self._json({"ok": True})
        else:
            self._json({"error": "no encontrado"}, 404)

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q: queue.Queue = queue.Queue()
        with HUB.lock:
            backlog = list(HUB.history)
            HUB.subscribers.append(q)
        try:
            self._send_event("hello", {"running": HUB.running})
            for kind, data in backlog:
                self._send_event(kind, data)
            while True:
                try:
                    kind, data = q.get(timeout=15)
                    self._send_event(kind, data)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # mantiene viva la conexión
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with HUB.lock:
                if q in HUB.subscribers:
                    HUB.subscribers.remove(q)

    def _send_event(self, kind: str, data: dict) -> None:
        self.wfile.write(f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jevjam.app", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    load_dotenv()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{args.port}"
    print(f"JEVjam en {url}  (Ctrl+C para cerrar)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        HUB.stop()
        if HUB.thread:
            HUB.thread.join(timeout=15)  # deja guardar la grabación
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
