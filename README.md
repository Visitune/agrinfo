# AGRINFO Auto-Scraper

Automatic fetching and archiving of EU AGRI-Food policy updates from [AGRINFO.eu](https://agrinfo.eu).

## Architecture

```
[AGRINFO.eu] ──► [scraper.py] ──► [SQLite (data/agrinfo.db)]
     │                │                    │
     │           GitHub Actions         ──► [index.html dashboard]
     │           (daily cron)           ──► [JSON export (data/articles/)]
     │
     └──► [api.py] ──► Serves data to dashboard
```

### Stack
- **SQLite** — incremental database (articles, publications, tags, normalized)
- **BeautifulSoup** — HTML parsing
- **Python http.server** — lightweight API for the dashboard
- **GitHub Actions** — daily cron job (06:00 UTC)
- **GitHub Pages** — static hosting (optional)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize the database
python -c "import database; database.init_db(); print('DB ready')"

# 3. Run the scraper
python scraper.py

# 4. Serve the dashboard (in another terminal)
python api.py

# 5. Open http://localhost:8080 in your browser
```

## How It Works

**`scraper.py`** fetches the AGRINFO homepage (articles) and `/publications/` page, parses the HTML with BeautifulSoup, and saves each item to:
- **SQLite** (`data/agrinfo.db`) — upsert (INSERT OR UPDATE), normalized schema with tags junction table
- **JSON** (`data/articles/*.json`) — flat backup, one file per item

**`database.py`** provides the data layer:
- `init_db()` — creates tables if not exists
- `upsert_article(data)` / `upsert_publication(data)` — incremental writes
- `query_articles(filters, limit, offset)` — filterable queries (tag, regulation, search, date range)
- `query_publications(filters, limit, offset)` — publication queries
- `stats()` — database statistics
- `export_json()` — full export to JSON

**`api.py`** serves the data via a lightweight HTTP API:
- `GET /api/articles?tag=Animal%20diseases&limit=20` — list articles (filterable, paginated)
- `GET /api/publications` — list publications
- `GET /api/stats` — statistics
- `GET /api/tags` — all tags
- `GET /api/search?q=pesticide` — full-text search

**`index.html`** is a static dashboard that connects to `api.py` and renders a filterable, responsive card grid.

## Database Schema

```sql
articles(id, title, url, pub_date, revised_date, regulation, summary, source, fetched_at)
publications(id, title, url, pub_date, description, category, source, fetched_at)
tags(id, name)                          -- normalized tag list
article_tags(article_id, tag_id)        -- many-to-many junction
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGRINFO_URL` | `https://agrinfo.eu` | Base URL to scrape |
| `AGRINFO_DATA_DIR` | `data/articles` | JSON output directory |
| `AGRINFO_DB` | `data/agrinfo.db` | SQLite database path |
| `AGRINFO_MAX_PAGES` | `3` | Homepage pages to scrape |
| `AGRINFO_API_HOST` | `0.0.0.0` | API server host |
| `AGRINFO_API_PORT` | `8080` | API server port |

## Deployment

### GitHub Pages + GitHub Actions
1. Push this repo to GitHub
2. GitHub Actions runs `python scraper.py` daily at 06:00 UTC
3. New articles are auto-committed to the repo
4. Enable GitHub Pages to serve `index.html`

### Local Development
```bash
# Terminal 1: scraper
python scraper.py

# Terminal 2: API server
python api.py

# Browser: http://localhost:8080
```

### Export to JSON
```python
import database
import json
data = database.export_json()
print(json.dumps(data, indent=2, ensure_ascii=False))
```

## Data Model

Each article has:
- `id` — unique slug
- `title` — article title
- `url` — full URL to the original
- `pub_date` — publication date (ISO format: YYYY-MM-DD)
- `revised_date` — revision date if applicable
- `regulation` — EU regulation number (e.g., 2026/278)
- `summary` — text summary
- `tags` — topic tags (Animal diseases, Food safety, etc.)
- `category` — publication type (for /publications/)
- `fetched_at` — timestamp of fetch