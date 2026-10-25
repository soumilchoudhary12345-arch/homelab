#!/usr/bin/env python3
"""songpage - a tiny progressive-streaming music page.

Serves one track with real HTTP Range support (206 Partial Content), so the
browser streams and seeks instead of downloading the whole file first.
"""
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(HERE, "track.mp3")
TRACK = os.environ.get(
    "TRACK_FILE",
    BUNDLED if os.path.isfile(BUNDLED) else "/home/soumil/music/aria-math.mp3",
)
COVER = os.path.join(HERE, "cover.jpg")
INDEX = os.path.join(HERE, "index.html")
CSS = os.path.join(HERE, "style.css")
FONTS_CSS = os.path.join(HERE, "fonts.css")
FONTS_DIR = os.path.join(HERE, "fonts")
FAVICON = os.path.join(HERE, "favicon.svg")
PORT = int(os.environ.get("PLAYER_PORT") or os.environ.get("PORT") or "8080")
BIND = os.environ.get("PLAYER_BIND", "0.0.0.0")
CHUNK = 1 << 16

META = {
    "TITLE": os.environ.get("TRACK_TITLE", "Aria Math"),
    "ARTIST": os.environ.get("TRACK_ARTIST", "C418"),
    "ALBUM": os.environ.get("TRACK_ALBUM", "Minecraft - Volume Beta"),
}


def read_index():
    with open(INDEX, "r", encoding="utf-8") as f:
        html = f.read()
    for k, v in META.items():
        html = html.replace("{{%s}}" % k, v)
    return html


class Handler(BaseHTTPRequestHandler):
    server_version = "songpage/1.0"
    protocol_version = "HTTP/1.1"

    def _small(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _send_file(self, path, ctype, head_only=False):
        if not os.path.isfile(path):
            self._small(404, "text/plain; charset=utf-8", b"not found")
            return
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if head_only:
            return
        try:
            with open(path, "rb") as f:
                while True:
                    c = f.read(CHUNK)
                    if not c:
                        break
                    self.wfile.write(c)
        except BrokenPipeError:
            pass

    def _stream_track(self, head_only=False):
        if not os.path.isfile(TRACK):
            self._small(404, "text/plain; charset=utf-8", b"not found")
            return
        size = os.path.getsize(TRACK)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng and rng.startswith("bytes="):
            spec = rng[6:].split(",")[0].strip()
            a, _, b = spec.partition("-")
            try:
                if a == "" and b != "":
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    if b != "":
                        end = int(b)
            except ValueError:
                start, end = 0, size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            partial = True
        length = end - start + 1
        if partial:
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        else:
            self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if head_only:
            return
        try:
            with open(TRACK, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    c = f.read(min(CHUNK, remaining))
                    if not c:
                        break
                    self.wfile.write(c)
                    remaining -= len(c)
        except BrokenPipeError:
            pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            self._small(200, "text/html; charset=utf-8", read_index().encode())
        elif p == "/style.css":
            self._send_file(CSS, "text/css; charset=utf-8")
        elif p == "/fonts.css":
            self._send_file(FONTS_CSS, "text/css; charset=utf-8")
        elif p == "/favicon.svg":
            self._send_file(FAVICON, "image/svg+xml")
        elif p.startswith("/fonts/"):
            name = os.path.basename(urllib.parse.unquote(p))
            if not name.endswith(".woff2") or "/" in name:
                self._small(404, "text/plain; charset=utf-8", b"not found")
            else:
                self._send_file(os.path.join(FONTS_DIR, name), "font/woff2")
        elif p == "/cover.jpg":
            self._send_file(COVER, "image/jpeg")
        elif p == "/track":
            self._stream_track()
        else:
            self._small(404, "text/plain; charset=utf-8", b"not found")

    def do_HEAD(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/track":
            self._stream_track(head_only=True)
        elif p == "/cover.jpg":
            self._send_file(COVER, "image/jpeg", head_only=True)
        elif p == "/style.css":
            self._send_file(CSS, "text/css; charset=utf-8", head_only=True)
        elif p == "/fonts.css":
            self._send_file(FONTS_CSS, "text/css; charset=utf-8", head_only=True)
        elif p == "/favicon.svg":
            self._send_file(FAVICON, "image/svg+xml", head_only=True)
        elif p in ("/", "/index.html"):
            self._small(200, "text/html; charset=utf-8", b"")
        else:
            self._small(404, "text/plain; charset=utf-8", b"")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("songpage serving %s on %s:%d" % (TRACK, BIND, PORT), flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
