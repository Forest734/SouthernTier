"""Dev server for public/ at http://localhost:8000 (or the port given).

Like `python3 -m http.server`, but tells the browser to check for a newer
copy of every file before using one it has, so edits show up on reload.
"""
import functools
import http.server
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


handler = functools.partial(Handler, directory="public")
with http.server.ThreadingHTTPServer(("localhost", PORT), handler) as server:
    print(f"Serving public/ at http://localhost:{PORT}")
    server.serve_forever()
