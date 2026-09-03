from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import urllib.parse
import database

HOST = os.environ.get("AGRINFO_API_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGRINFO_API_PORT", "8080"))


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/articles":
            self.serve_json(database.query_articles(
                filters=self._filters(qs),
                limit=int(qs.get("limit", ["50"])[0]),
                offset=int(qs.get("offset", ["0"])[0])
            ))
        elif path == "/api/publications":
            self.serve_json(database.query_publications(
                filters=self._filters(qs),
                limit=int(qs.get("limit", ["50"])[0]),
                offset=int(qs.get("offset", ["0"])[0])
            ))
        elif path == "/api/stats":
            self.serve_json(database.stats())
        elif path == "/api/tags":
            self.serve_json({"tags": [t[0] for t in database.get_db().execute("SELECT name FROM tags ORDER BY name").fetchall()]})
        elif path == "/api/search":
            q = qs.get("q", [""])[0]
            self.serve_json(database.query_articles(
                filters={"search": q},
                limit=20
            ))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            with open("index.html", "rb") as f:
                self.wfile.write(f.read())

    def _filters(self, qs):
        f = {}
        if qs.get("tag"):
            f["tag"] = qs["tag"][0]
        if qs.get("regulation"):
            f["regulation"] = qs["regulation"][0]
        if qs.get("search"):
            f["search"] = qs["search"][0]
        if qs.get("from_date"):
            f["from_date"] = qs["from_date"][0]
        if qs.get("to_date"):
            f["to_date"] = qs["to_date"][0]
        return f

    def serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    database.init_db()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"AGRINFO API serving on http://{HOST}:{PORT}")
    print(f"  /api/articles  - list articles (paginated, filterable)")
    print(f"  /api/publications - list publications")
    print(f"  /api/stats     - database statistics")
    print(f"  /api/tags      - all tags")
    print(f"  /api/search?q=... - full-text search")
    server.serve_forever()