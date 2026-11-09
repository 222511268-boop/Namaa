"""Stand-in Overpass API for end-to-end tests.

Answers every query with a response recorded from the real Overpass API
(backend/tests/fixtures/overpass_parks_al_rawdah.json), so E2E import tests are repeatable
and do not depend on the public service's availability.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURE = Path("/fixtures/overpass_parks_al_rawdah.json").read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(FIXTURE)))
        self.end_headers()
        self.wfile.write(FIXTURE)

    do_GET = do_POST  # noqa: N815


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
