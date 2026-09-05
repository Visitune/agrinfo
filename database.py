import sqlite3
import os
import re
import json
from datetime import datetime, timezone, date, timedelta

DB_PATH = os.environ.get("AGRINFO_DB", "data/agrinfo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    pub_date    TEXT,
    revised_date TEXT,
    regulation  TEXT,
    summary     TEXT,
    source      TEXT DEFAULT 'agrinfo.eu',
    fetched_at  TEXT NOT NULL,
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS publications (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    pub_date    TEXT,
    description TEXT,
    category    TEXT,
    source      TEXT DEFAULT 'agrinfo.eu',
    fetched_at  TEXT NOT NULL,
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id  TEXT NOT NULL,
    tag_id      INTEGER NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id),
    UNIQUE(article_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_regulation ON articles(regulation);
CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title);
CREATE INDEX IF NOT EXISTS idx_publications_pub_date ON publications(pub_date DESC);
CREATE INDEX IF NOT EXISTS idx_publications_category ON publications(category);
"""

DETAIL_COLUMNS = [
    ("impacted_products", "TEXT DEFAULT ''"),
    ("what_changing", "TEXT DEFAULT ''"),
    ("why", "TEXT DEFAULT ''"),
    ("timeline", "TEXT DEFAULT ''"),
    ("actions", "TEXT DEFAULT ''"),
    ("background", "TEXT DEFAULT ''"),
    ("detail_summary", "TEXT DEFAULT ''"),
    ("eurlex_url", "TEXT DEFAULT ''"),
    ("detail_fetched_at", "TEXT DEFAULT ''"),
    ("title_fr", "TEXT DEFAULT ''"),
    ("summary_fr", "TEXT DEFAULT ''"),
    ("impacted_products_fr", "TEXT DEFAULT ''"),
    ("timeline_fr", "TEXT DEFAULT ''"),
    ("actions_fr", "TEXT DEFAULT ''"),
    ("translated_at", "TEXT DEFAULT ''"),
]

def migrate():
    """Ajoute les colonnes detail si DB deja existante."""
    conn = get_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
    for name, ddl in DETAIL_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {name} {ddl}")
    conn.commit()
    conn.close()

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    migrate()

def upsert_article(data):
    migrate()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (id, title, url, pub_date, revised_date, regulation, summary,
            impacted_products, what_changing, why, timeline, actions, background,
            detail_summary, eurlex_url, detail_fetched_at,
            title_fr, summary_fr, impacted_products_fr, timeline_fr, actions_fr, translated_at,
            fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            url=excluded.url,
            pub_date=excluded.pub_date,
            revised_date=excluded.revised_date,
            regulation=excluded.regulation,
            summary=excluded.summary,
            impacted_products=excluded.impacted_products,
            what_changing=excluded.what_changing,
            why=excluded.why,
            timeline=excluded.timeline,
            actions=excluded.actions,
            background=excluded.background,
            detail_summary=excluded.detail_summary,
            eurlex_url=excluded.eurlex_url,
            detail_fetched_at=excluded.detail_fetched_at,
            title_fr=CASE WHEN excluded.title_fr != '' THEN excluded.title_fr ELSE title_fr END,
            summary_fr=CASE WHEN excluded.summary_fr != '' THEN excluded.summary_fr ELSE summary_fr END,
            impacted_products_fr=CASE WHEN excluded.impacted_products_fr != '' THEN excluded.impacted_products_fr ELSE impacted_products_fr END,
            timeline_fr=CASE WHEN excluded.timeline_fr != '' THEN excluded.timeline_fr ELSE timeline_fr END,
            actions_fr=CASE WHEN excluded.actions_fr != '' THEN excluded.actions_fr ELSE actions_fr END,
            translated_at=CASE WHEN excluded.translated_at != '' THEN excluded.translated_at ELSE translated_at END,
            fetched_at=excluded.fetched_at
    """, (
        data["id"], data["title"], data["url"],
        data.get("pub_date"), data.get("revised_date"),
        data.get("regulation", ""), data.get("summary", ""),
        data.get("impacted_products", ""), data.get("what_changing", ""),
        data.get("why", ""), data.get("timeline", ""), data.get("actions", ""),
        data.get("background", ""), data.get("detail_summary", ""),
        data.get("eurlex_url", ""), data.get("detail_fetched_at", ""),
        data.get("title_fr", ""), data.get("summary_fr", ""),
        data.get("impacted_products_fr", ""), data.get("timeline_fr", ""),
        data.get("actions_fr", ""), data.get("translated_at", ""),
        data.get("fetched_at", datetime.now(timezone.utc).isoformat())
    ))

    if data.get("tags"):
        cur.execute("DELETE FROM article_tags WHERE article_id = ?", (data["id"],))
        for tag_name in data["tags"]:
            cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cur.fetchone()[0]
            cur.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?, ?)", (data["id"], tag_id))

    conn.commit()
    conn.close()

def upsert_publication(data):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO publications (id, title, url, pub_date, description, category, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            url=excluded.url,
            pub_date=excluded.pub_date,
            description=excluded.description,
            category=excluded.category,
            fetched_at=excluded.fetched_at
    """, (
        data["id"], data["title"], data["url"],
        data.get("pub_date"), data.get("description", ""),
        data.get("category", ""),
        data.get("fetched_at", datetime.now(timezone.utc).isoformat())
    ))
    conn.commit()
    conn.close()

def query_articles(filters=None, limit=50, offset=0):
    conn = get_db()
    query = "SELECT * FROM articles a WHERE 1=1"
    params = []
    if filters:
        if filters.get("tag"):
            query = """
                SELECT a.* FROM articles a
                JOIN article_tags at ON a.id = at.article_id
                JOIN tags t ON at.tag_id = t.id
                WHERE t.name = ?
            """
            params.append(filters["tag"])
        if filters.get("regulation"):
            query += " AND a.regulation LIKE ?"
            params.append(f"%{filters['regulation']}%")
        if filters.get("search"):
            query += " AND (a.title LIKE ? OR a.summary LIKE ? OR a.regulation LIKE ? OR a.impacted_products LIKE ? OR a.what_changing LIKE ? OR a.timeline LIKE ? OR a.actions LIKE ?)"
            params.extend([f"%{filters['search']}%"] * 7)
        if filters.get("from_date"):
            query += " AND a.pub_date >= ?"
            params.append(filters["from_date"])
        if filters.get("to_date"):
            query += " AND a.pub_date <= ?"
            params.append(filters["to_date"])

    query += " ORDER BY COALESCE(a.pub_date, '') DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    articles = [dict(r) for r in rows]
    # Attache les tags (le front filtre dessus)
    for a in articles:
        try:
            trows = conn.execute(
                "SELECT t.name FROM tags t JOIN article_tags at ON t.id = at.tag_id WHERE at.article_id = ? ORDER BY t.name",
                (a["id"],),
            ).fetchall()
            a["tags"] = [t[0] for t in trows]
        except Exception:
            a["tags"] = []
    conn.close()
    return articles

def query_publications(filters=None, limit=50, offset=0):
    conn = get_db()
    query = "SELECT * FROM publications WHERE 1=1"
    params = []
    if filters:
        if filters.get("category"):
            query += " AND category = ?"
            params.append(filters["category"])
        if filters.get("search"):
            query += " AND title LIKE ?"
            params.append(f"%{filters['search']}%")
    query += " ORDER BY COALESCE(pub_date, '') DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def stats():
    conn = get_db()
    result = {}
    result["total_articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    result["total_publications"] = conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0]
    result["total_tags"] = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    result["articles_with_regulation"] = conn.execute("SELECT COUNT(*) FROM articles WHERE regulation != ''").fetchone()[0]
    result["latest_article_date"] = conn.execute("SELECT MAX(pub_date) FROM articles").fetchone()[0]
    result["oldest_article_date"] = conn.execute("SELECT MIN(pub_date) FROM articles").fetchone()[0]
    result["unique_regulations"] = conn.execute("SELECT COUNT(DISTINCT regulation) FROM articles WHERE regulation != ''").fetchone()[0]
    try:
        result["articles_with_detail"] = conn.execute("SELECT COUNT(*) FROM articles WHERE timeline != '' OR impacted_products != ''").fetchone()[0]
        result["articles_with_timeline"] = conn.execute("SELECT COUNT(*) FROM articles WHERE timeline != ''").fetchone()[0]
    except Exception:
        result["articles_with_detail"] = 0
        result["articles_with_timeline"] = 0
    conn.close()
    try:
        cons = consultations_list()
        result["open_consultations"] = sum(1 for c in cons if c["open"])
        result["total_consultations"] = len(cons)
        result["fresh_7d"] = len(fresh_list(7))
        result["calendar_events"] = len(calendar_list())
    except Exception:
        pass
    return result

def export_json():
    conn = get_db()
    articles = conn.execute("SELECT * FROM articles ORDER BY pub_date DESC").fetchall()
    publications = conn.execute("SELECT * FROM publications ORDER BY pub_date DESC").fetchall()
    tags = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    articles = [dict(a) for a in articles]
    for a in articles:
        trows = conn.execute(
            "SELECT t.name FROM tags t JOIN article_tags at ON t.id = at.tag_id WHERE at.article_id = ? ORDER BY t.name",
            (a["id"],),
        ).fetchall()
        a["tags"] = [t[0] for t in trows]
    conn.close()
    try:
        consultations = consultations_list()
    except Exception:
        consultations = []
    try:
        calendar = calendar_list()
    except Exception:
        calendar = []
    return {
        "articles": articles,
        "publications": [dict(p) for p in publications],
        "tags": [t[0] for t in tags],
        "consultations": consultations,
        "calendar": calendar,
        "exported_at": datetime.now(timezone.utc).isoformat()
    }


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

def _parse_day_month_year(text):
    """16 September 2026 -> 2026-09-16. Retourne None si absent."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.I)
    if not m:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def _parse_quarter(text):
    """fourth quarter of 2026 -> 2026-10-01 (approx)."""
    if not text:
        return None
    m = re.search(r"(first|second|third|fourth)\s+quarter\s+of\s+(\d{4})", text, re.I)
    if not m:
        return None
    q = {"first": "01-01", "second": "04-01", "third": "07-01", "fourth": "10-01"}[m.group(1).lower()]
    return f"{m.group(2)}-{q}"


def consultation_deadline(article):
    """Deadline de consultation (Have Your Say / feedback). None si pas une consultation."""
    blob = " ".join([article.get("title", ""), article.get("what_changing", ""),
                     article.get("actions", ""), article.get("timeline", "")])
    if not re.search(r"consultation|have your say|give feedback|feedback|invite.*comment", blob, re.I):
        return None
    # Date pres d'un mot-cle de deadline (until/by/before/closed on/closes/deadline)
    for field in ("actions", "what_changing", "timeline", "summary"):
        txt = article.get(field, "") or ""
        m = re.search(
            r"(until|by|before|deadline|closed?\s+on|closes?|open\s+until)\b[^.]{0,60}?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            txt, re.I)
        if m:
            try:
                return date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(2))).isoformat()
            except ValueError:
                continue
    return None


def consultations_list():
    """Articles de type consultation avec deadline + statut open/closed."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles").fetchall()
    conn.close()
    today = date.today().isoformat()
    out = []
    for r in rows:
        a = dict(r)
        dl = consultation_deadline(a)
        if dl is None:
            # consultation sans date explicite -> on la garde quand meme
            blob = " ".join([a.get("title", ""), a.get("actions", "")])
            if not re.search(r"consultation|have your say|feedback", blob, re.I):
                continue
        out.append({
            "id": a["id"], "title": a["title"], "url": a["url"],
            "deadline": dl, "open": (dl is None or dl >= today),
            "impacted_products": a.get("impacted_products", ""),
            "timeline": (a.get("timeline", "") or "")[:300],
        })
    out.sort(key=lambda x: (x["deadline"] is None, x["deadline"] or ""))
    return out


def timeline_date(article):
    """Date normalisee depuis le champ timeline (jour precis ou trimestre)."""
    tl = article.get("timeline", "") or ""
    d = _parse_day_month_year(tl)
    if d:
        return d
    q = _parse_quarter(tl)
    if q:
        return q
    m = re.search(r"from\s+(\d{4})\b", tl)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def calendar_list():
    """Articles tries par date d'entree en vigueur estimee."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE timeline != ''").fetchall()
    conn.close()
    out = []
    for r in rows:
        a = dict(r)
        d = timeline_date(a)
        if d:
            out.append({
                "id": a["id"], "title": a["title"], "url": a["url"],
                "timeline_date": d, "timeline": a.get("timeline", "")[:300],
                "regulation": a.get("regulation", ""),
                "impacted_products": a.get("impacted_products", "")[:150],
            })
    out.sort(key=lambda x: x["timeline_date"])
    return out


def fresh_list(days=7):
    """Nouveautes : pub_date dans les N derniers jours (vs site officiel sans alerte)."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles ORDER BY pub_date DESC").fetchall()
    conn.close()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    out = []
    for r in rows:
        a = dict(r)
        if (a.get("pub_date") or "") >= cutoff:
            out.append(a)
    return out