import sqlite3
import os
import json
from datetime import datetime, timezone

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

def upsert_article(data):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (id, title, url, pub_date, revised_date, regulation, summary, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            url=excluded.url,
            pub_date=excluded.pub_date,
            revised_date=excluded.revised_date,
            regulation=excluded.regulation,
            summary=excluded.summary,
            fetched_at=excluded.fetched_at
    """, (
        data["id"], data["title"], data["url"],
        data.get("pub_date"), data.get("revised_date"),
        data.get("regulation", ""), data.get("summary", ""),
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
            query += " AND a.title LIKE ?"
            params.append(f"%{filters['search']}%")
        if filters.get("from_date"):
            query += " AND a.pub_date >= ?"
            params.append(filters["from_date"])
        if filters.get("to_date"):
            query += " AND a.pub_date <= ?"
            params.append(filters["to_date"])

    query += " ORDER BY COALESCE(a.pub_date, '') DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

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
    conn.close()
    return result

def export_json():
    conn = get_db()
    articles = conn.execute("SELECT * FROM articles ORDER BY pub_date DESC").fetchall()
    publications = conn.execute("SELECT * FROM publications ORDER BY pub_date DESC").fetchall()
    tags = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    conn.close()
    return {
        "articles": [dict(a) for a in articles],
        "publications": [dict(p) for p in publications],
        "tags": [t[0] for t in tags],
        "exported_at": datetime.now(timezone.utc).isoformat()
    }