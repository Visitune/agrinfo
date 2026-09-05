from http.server import HTTPServer, SimpleHTTPRequestHandler
import html
import json
import os
import urllib.parse
from datetime import datetime, timezone
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
            conn = database.get_db()
            try:
                rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
                self.serve_json({"tags": [t[0] for t in rows]})
            finally:
                conn.close()
        elif path == "/api/search":
            q = qs.get("q", [""])[0]
            self.serve_json(database.query_articles(
                filters={"search": q},
                limit=20
            ))
        elif path == "/api/consultations":
            # Tracker consultations UE : deadlines Have Your Say
            self.serve_json(database.consultations_list())
        elif path == "/api/fresh":
            # Veille nouveautes : ?days=30 par defaut (7j souvent vide)
            days = int(qs.get("days", ["30"])[0])
            self.serve_json(database.fresh_list(days))
        elif path == "/api/calendar":
            # Calendrier entrees en vigueur (parse des Timelines)
            self.serve_json(database.calendar_list())
        elif path in ("/rss", "/rss.xml", "/api/rss"):
            self.serve_rss()
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

    def serve_rss(self):
        """Flux RSS des 20 derniers articles (veille sans dependre du site officiel)."""
        items = database.query_articles(limit=20)
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<rss version="2.0"><channel>',
                 "<title>AGRINFO Veille — EU Agri-Food</title>",
                 "<link>https://agrinfo.eu/</link>",
                 "<description>Nouveautes AGRINFO enrichies : produits, timeline, consultations</description>",
                 f"<lastBuildDate>{now}</lastBuildDate>"]
        for a in items:
            title = html.escape(a.get("title", ""))
            link = html.escape(a.get("url", ""))
            desc = html.escape((a.get("summary", "") or "")[:400])
            pub = html.escape(a.get("pub_date", "") or "")
            parts.append(f"<item><title>{title}</title><link>{link}</link>"
                         f"<description>{desc}</description><pubDate>{pub}</pubDate>"
                         f"<guid>{link}</guid></item>")
        parts.append("</channel></rss>")
        body = "\n".join(parts).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    database.init_db()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"AGRINFO API serving on http://{HOST}:{PORT}")
    print(f"  /api/articles  - list articles (paginated, filterable)")
    print(f"  /api/publications - list publications")
    print(f"  /api/stats     - database statistics")
    print(f"  /api/tags      - all tags")
    print(f"  /api/search?q=... - full-text search")
    print(f"  /api/consultations - tracker consultations UE (deadlines)")
    print(f"  /api/fresh?days=30 - veille nouveautes")
    print(f"  /api/calendar  - calendrier entrees en vigueur")
    print(f"  /rss           - flux RSS veille")
    server.serve_forever()