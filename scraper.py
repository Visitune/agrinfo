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
    # NOTE: on agrinfo.eu le <article class="report-card"> est ENVELOPPE
    # dans un <a href="...book-of-reports...">, pas l'inverse.
    # On itère donc sur les <a> parents.
    for link_el in soup.select("a:has(article.report-card)"):
        article = link_el.select_one("article.report-card")
        if article is None:
            continue
        url = link_el.get("href", "")
        if not url or url.startswith("mailto:"):
            continue
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

        tags = [t.get_text(strip=True) for t in article.select(".topic-tag")]
        # filtre les tags vides (le parsing précédent retournait parfois '')
        tags = [t for t in tags if t]

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
        # NOTE: chaque carte contient 2 liens : un mailto:? (partage)
        # dont le body contient "/documents/..." + le vrai lien PDF.
        # On prend le premier lien non-mailto vers /documents/.
        url = ""
        for a in card.select('a[href*="/documents/"]'):
            href = a.get("href", "")
            if href and not href.startswith("mailto:"):
                url = href
                break
        if not url:
            continue
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


def extract_detail(html):
    """Parse une fiche /book-of-reports/... en sections structurees.

    Le site officiel oblige a ouvrir chaque fiche : on en extrait
    Produits impactes, Timeline, Actions recommandees, lien EUR-Lex, etc.
    Retourne un dict avec des chaines ('' si absent).
    """
    soup = BeautifulSoup(html, "html.parser")
    # Zone "full report" (onglet Full) ; fallback = page entiere
    full = None
    for div in soup.select("div[x-show]"):
        if "full" in (div.get("x-show") or ""):
            full = div
            break
    scope = full if full is not None else soup

    mapping = {
        "update": "update",
        "impacted products": "impacted_products",
        "what is changing": "what_changing",
        "why": "why",
        "timeline": "timeline",
        "recommended actions": "actions",
        "background": "background",
        "resources": "resources",
        "summary": "detail_summary",
    }
    sections = {v: "" for v in mapping.values()}

    for h3 in scope.select("h3"):
        key = h3.get_text(strip=True).lower().rstrip("?").strip()
        field = mapping.get(key) or mapping.get(key.rstrip("?"))
        if not field:
            continue
        parts = []
        for sib in h3.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            if sib.name in ("p", "div", "ul", "ol", "blockquote"):
                txt = sib.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
        sections[field] = "\n\n".join(parts)[:4000]

    # Summary (onglet Summary) si pas deja rempli
    if not sections["detail_summary"]:
        h2 = scope.find(["h1", "h2"], string=lambda s: s and "summary" in s.lower())
        if h2:
            nxt = h2.find_next("p")
            if nxt:
                sections["detail_summary"] = nxt.get_text(" ", strip=True)[:2000]

    # Liens EUR-Lex (vrai texte juridique)
    eurlex = []
    for a in soup.select('a[href*="eur-lex.europa.eu"]'):
        href = a.get("href", "")
        if href and href not in eurlex:
            eurlex.append(href)
    sections["eurlex_urls"] = eurlex[:5]
    sections["eurlex_url"] = eurlex[0] if eurlex else ""
    return sections


def fetch_detail(url):
    """Recupere + parse une fiche detail. Retourne {} en cas d'erreur."""
    try:
        html = fetch_page(url)
    except requests.RequestException as e:
        print(f"    [!] detail fetch failed {url}: {e}")
        return {}
    try:
        return extract_detail(html)
    except Exception as e:
        print(f"    [!] detail parse failed {url}: {e}")
        return {}


TRANSLATE_QUOTA_OK = True

def translate_en_fr(text, max_chars=450):
    """Traduit EN->FR via MyMemory (gratuit, sans cle). Cache en DB.
    Retourne '' si quota epuise ou erreur (le front traduira a la volee)."""
    global TRANSLATE_QUOTA_OK
    if not TRANSLATE_QUOTA_OK or not text or not text.strip():
        return ""
    text = text.strip()[:max_chars]
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|fr"},
            headers=HEADERS, timeout=20)
        r.raise_for_status()
        payload = r.json()
        if payload.get("quotaFinished"):
            TRANSLATE_QUOTA_OK = False
            print("    [!] quota traduction FR epuise (MyMemory) — suite en EN, front en live")
            return ""
        out = (payload.get("responseData") or {}).get("translatedText", "")
        if not out or out.upper().startswith("QUERY LENGTH LIMIT"):
            return ""
        return out
    except requests.RequestException as e:
        print(f"    [!] traduction FR failed: {e}")
        return ""


def save_article(article):
    json_path = os.path.join(DATA_DIR, f"{article['id']}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    database.upsert_article(article)


def save_publication(pub):
    json_path = os.path.join(DATA_DIR, f"{pub['id']}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=2)

    database.upsert_publication(pub)


def get_index(base_url, page=1):
    if page == 1:
        return f"{base_url.rstrip('/')}/"
    return f"{base_url.rstrip('/')}/?page={page}"


def write_rss_xml(articles, path="data/rss.xml"):
    """Flux RSS statique pour GitHub Pages (veille)."""
    import html as _html
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0"><channel>',
             "<title>AGRINFO Veille — EU Agri-Food</title>",
             "<link>https://agrinfo.eu/</link>",
             "<description>Nouveautes AGRINFO enrichies : produits, timeline, consultations</description>",
             f"<lastBuildDate>{now}</lastBuildDate>"]
    for a in sorted(articles, key=lambda x: x.get("pub_date", ""), reverse=True)[:20]:
        title = _html.escape(a.get("title", ""))
        link = _html.escape(a.get("url", ""))
        desc = _html.escape((a.get("summary", "") or "")[:400])
        pub = _html.escape(a.get("pub_date", "") or "")
        parts.append(f"<item><title>{title}</title><link>{link}</link>"
                     f"<description>{desc}</description><pubDate>{pub}</pubDate>"
                     f"<guid>{link}</guid></item>")
    parts.append("</channel></rss>")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


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
    fetch_detail_flag = os.environ.get("AGRINFO_FETCH_DETAIL", "1") == "1"
    translate_flag = os.environ.get("AGRINFO_TRANSLATE_FR", "1") == "1"
    for item in articles:
        if fetch_detail_flag and "/book-of-reports/" in item.get("url", ""):
            detail = fetch_detail(item["url"])
            if detail:
                item.update(detail)
                item["detail_fetched_at"] = datetime.now(timezone.utc).isoformat()
        if translate_flag:
            # Titres FR au scrape (court, tient dans le quota) ; le reste en live front
            tfr = translate_en_fr(item.get("title", ""), 200)
            if tfr:
                item["title_fr"] = tfr
            sfr = translate_en_fr(item.get("summary", ""), 450)
            if sfr:
                item["summary_fr"] = sfr
            if TRANSLATE_QUOTA_OK:
                pfr = translate_en_fr(item.get("impacted_products", ""), 200)
                if pfr:
                    item["impacted_products_fr"] = pfr
            if item.get("title_fr"):
                item["translated_at"] = datetime.now(timezone.utc).isoformat()
        save_article(item)
        extra = " +detail" if item.get("impacted_products") or item.get("timeline") else ""
        extra += " +FR" if item.get("title_fr") else ""
        print(f"  🆕 Article: {item['title'][:60]}{extra}")
    for item in publications:
        save_publication(item)
        print(f"  🆕 Publication: {item['title'][:60]}")
    new_json = len(all_items)

    index_path = os.path.join(DATA_DIR, "_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(all_items),
            "articles": [a["id"] for a in articles],
            "publications": [p["id"] for p in publications],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, f, ensure_ascii=False, indent=2)

    db_stats = database.stats()
    write_rss_xml(articles)
    # Export statique pour GitHub Pages (pas de serveur API la-bas)
    export = database.export_json()
    with open("data/export.json", "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=1)
    print(f"\n[+] Done. {len(all_items)} items processed.")
    print(f"    SQLite: {db_stats['total_articles']} articles, {db_stats['total_publications']} publications")
    print(f"    Tags: {db_stats['total_tags']} unique")
    print(f"    Regulations: {db_stats['unique_regulations']} unique")
    print(f"    Consultations: {db_stats.get('open_consultations', 0)} ouvertes / {db_stats.get('total_consultations', 0)} total")
    print(f"    Calendrier: {db_stats.get('calendar_events', 0)} echeances | Fraiches 30j: {len(database.fresh_list(30))}")
    print(f"    RSS: data/rss.xml")


if __name__ == "__main__":
    main()