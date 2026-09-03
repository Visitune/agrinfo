import os
import json
import re
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import database

URL = os.environ.get("AGRINFO_URL", "https://agrinfo.eu")
DATA_DIR = os.environ.get("AGRINFO_DATA_DIR", "data/articles")
HEADERS = {
    "User-Agent": "AgrinfoNewsBot/1.0 (+https://github.com/agrinfo-scraper)"
}
MAX_PAGES = int(os.environ.get("AGRINFO_MAX_PAGES", "3"))

os.makedirs(DATA_DIR, exist_ok=True)


def slugify(url):
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r'[^a-z0-9\-]', '_', slug.lower())
    return slug


def parse_date(date_str):
    formats = [
        "%b. %d, %Y",
        "%b. %d %Y",
        "%B %d, %Y",
        "%d %B %Y",
        "%Y-%m-%d",
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def fetch_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_articles_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    for article in soup.select("article.report-card"):
        link_el = article.select_one("a[href]")
        if not link_el:
            continue
        url = link_el["href"]
        if not url.startswith("http"):
            url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

        slug = slugify(url)
        title_el = article.select_one("h2")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        date_el = article.select_one("time")
        pub_date = date_el["datetime"] if date_el and date_el.has_attr("datetime") else ""
        if not pub_date and date_el:
            pub_date = date_el.get_text(strip=True)
        pub_date = parse_date(pub_date) if pub_date else ""

        revised_el = article.select_one("time[datetime]:nth-of-type(2)")
        revised_date = ""
        if revised_el and revised_el.has_attr("datetime"):
            revised_date = revised_el["datetime"]

        summary_el = article.select_one(".content p, .content [data-block-key]")
        summary = ""
        if summary_el:
            summary = summary_el.get_text(strip=True)[:500]

        regulation_el = article.select_one(".regulation-tag")
        regulation = regulation_el.get_text(strip=True) if regulation_el else ""

        tags = [t.get_text(strip=True) for t in article.select(".content .topic-tag, footer .topic-tag")]

        if not summary:
            p_els = article.select("p")
            for p in p_els:
                txt = p.get_text(strip=True)
                if txt and len(txt) > 20:
                    summary = txt[:500]
                    break

        articles.append({
            "id": slug,
            "title": title,
            "url": url,
            "pub_date": pub_date,
            "revised_date": revised_date,
            "regulation": regulation,
            "summary": summary,
            "tags": tags,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return articles


def extract_publications_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    publications = []
    for card in soup.select(".bg-white.rounded-xl"):
        link_el = card.select_one("a[href]")
        if not link_el or "/documents/" not in link_el["href"]:
            continue
        url = link_el["href"]
        if not url.startswith("http"):
            url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

        slug = slugify(url)
        title_el = card.select_one("h2")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        date_el = card.select_one(".flex.items-center.text-sm.text-gray-600")
        pub_date = ""
        if date_el:
            pub_date = date_el.get_text(strip=True)

        desc_el = card.select_one(".text-gray-600")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        category_el = card.select_one(".bg-blue-50")
        category = category_el.get_text(strip=True) if category_el else ""

        publications.append({
            "id": slug,
            "title": title,
            "url": url,
            "pub_date": pub_date,
            "description": description,
            "category": category,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return publications


def save_article(article):
    json_path = os.path.join(DATA_DIR, f"{article['id']}.json")
    if not os.path.exists(json_path):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

    database.upsert_article(article)


def save_publication(pub):
    json_path = os.path.join(DATA_DIR, f"{pub['id']}.json")
    if not os.path.exists(json_path):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(pub, f, ensure_ascii=False, indent=2)

    database.upsert_publication(pub)


def get_index(base_url, page=1):
    if page == 1:
        return f"{base_url.rstrip('/')}/"
    return f"{base_url.rstrip('/')}/?page={page}"


def main():
    database.init_db()
    base_url = URL
    articles = []
    publications = []
    new_json = 0
    new_db = 0

    for page in range(1, MAX_PAGES + 1):
        url = get_index(base_url, page)
        print(f"[+] Fetching {url}")
        try:
            html = fetch_page(url)
        except requests.RequestException as e:
            print(f"[!] Error fetching {url}: {e}")
            break

        extracted = extract_articles_from_html(html, base_url)
        if not extracted:
            print(f"[!] No articles found on page {page}, stopping.")
            break

        articles.extend(extracted)
        print(f"    Found {len(extracted)} articles on page {page}")

        if len(extracted) < 2:
            break

    pub_html = fetch_page(f"{base_url.rstrip('/')}/publications/")
    pubs = extract_publications_from_html(pub_html, base_url)
    publications.extend(pubs)
    print(f"[+] Found {len(pubs)} publications on /publications/")

    all_items = articles + publications
    for item in all_items:
        if item.get("tags") or item.get("regulation"):
            save_article(item)
            new_json += 1
            print(f"  🆕 Article: {item['title'][:60]}")
        else:
            save_publication(item)
            new_json += 1
            print(f"  🆕 Publication: {item['title'][:60]}")

    index_path = os.path.join(DATA_DIR, "_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(all_items),
            "articles": [a["id"] for a in articles],
            "publications": [p["id"] for p in publications],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, f, ensure_ascii=False, indent=2)

    db_stats = database.stats()
    print(f"\n[+] Done. {len(all_items)} items processed.")
    print(f"    SQLite: {db_stats['total_articles']} articles, {db_stats['total_publications']} publications")
    print(f"    Tags: {db_stats['total_tags']} unique")
    print(f"    Regulations: {db_stats['unique_regulations']} unique")


if __name__ == "__main__":
    main()