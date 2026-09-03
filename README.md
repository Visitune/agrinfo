# AGRINFO Auto-Scraper

Automatic fetching and archiving of EU AGRI-Food policy updates from [AGRINFO.eu](https://agrinfo.eu).

## Architecture

```
[AGRINFO.eu] ──► [scraper.py] ──► [data/articles/*.json] ──► [index.html]
     │                │                    │                        │
     │           GitHub Actions        Git repo               Static site
     │           (daily cron)         (versioned)            (GitHub Pages)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the scraper
python scraper.py

# 3. Open index.html in a browser
```

## How It Works

**`scraper.py`** fetches the AGRINFO homepage and publications page, parses the HTML with BeautifulSoup, and saves each new article/publication as a JSON file in `data/articles/`. Articles that already exist are skipped (idempotent).

**`.github/workflows/update.yml`** runs the scraper daily at 06:00 UTC via GitHub Actions and auto-commits new articles to the repository.

**`index.html`** is a static dashboard that loads the JSON data and renders a filterable, responsive card grid. Deploy it on GitHub Pages for a free, always-up-to-date website.

## Data Model

Each article JSON contains:
- `id` — unique slug
- `title` — article title
- `url` — full URL to the original
- `pub_date` — publication date (ISO format)
- `revised_date` — revision date if applicable
- `regulation` — EU regulation number (e.g., 2026/278)
- `summary` — text summary
- `tags` — topic tags (Animal diseases, Food safety, etc.)
- `category` — publication type (for /publications/)
- `fetched_at` — timestamp of fetch

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGRINFO_URL` | `https://agrinfo.eu` | Base URL to scrape |
| `AGRINFO_DATA_DIR` | `data/articles` | Output directory |
| `AGRINFO_MAX_PAGES` | `3` | Number of homepage pages to scrape |

## Deployment

### GitHub Pages
1. Push this repo to GitHub
2. Go to Settings → Pages → Source: GitHub Actions (or deploy with a static site builder)
3. The `index.html` will be live at `https://<user>.github.io/<repo>/`

### Manual
1. Run `python scraper.py`
2. Open `index.html` in a browser (data loads from `data/articles/` via fetch — needs a local server or the files must be in a web-accessible location)