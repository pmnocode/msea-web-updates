#!/usr/bin/env python3
"""
MapleSEA Updates Watcher
- Checks https://www.maplesea.com/updates for new links
- Posts to one or many Discord webhooks
- Supports per-webhook prefixes (e.g., <@USER_ID>, @everyone)
- Detects title changes on the listing page as "updates"
- Persists seen URLs and last known title in SQLite

Config priority:
1) config.json written by the workflow from GitHub Secrets:
   { "DISCORD_WEBHOOK_URLS": [ {"url":"...","prefix":"..."}, ... ] }
2) Fallback env vars for quick local testing:
   - DISCORD_WEBHOOK_URL            (single URL)
   - DISCORD_WEBHOOK_URLS_CSV       (comma-separated URLs)
"""

import os, sqlite3, re, json
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.maplesea.com/updates"
ALLOWED_HREF = re.compile(r"/updates(/|$)", re.IGNORECASE)
DB_PATH = os.environ.get("DB_PATH", "seen_links.db")
CONFIG_PATH = "config.json"

HEADERS = {
    "User-Agent": "MapleSEA-Updates-Watcher/1.2 (+https://github.com/your/repo)"
}
TIMEOUT = 20

# ---------- Config loading ----------

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"WARNING: Could not read {CONFIG_PATH}: {e}")

    webhooks = cfg.get("DISCORD_WEBHOOK_URLS")

    # Backward-compatible fallbacks for local/manual runs
    if not webhooks:
        single = os.environ.get("DISCORD_WEBHOOK_URL")
        if single:
            webhooks = [{"url": single, "prefix": ""}]
    if not webhooks:
        csv = os.environ.get("DISCORD_WEBHOOK_URLS_CSV")
        if csv:
            webhooks = [{"url": u.strip(), "prefix": ""} for u in csv.split(",") if u.strip()]

    cfg["DISCORD_WEBHOOK_URLS"] = webhooks or []
    return cfg

# ---------- DB helpers ----------

def init_db():
    """Create table if missing; add new columns if coming from older script."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_links (
            url TEXT PRIMARY KEY,
            first_seen_utc TEXT NOT NULL,
            last_title TEXT,
            last_changed_utc TEXT
        )
    """)
    for coldef in ("last_title TEXT", "last_changed_utc TEXT"):
        try:
            conn.execute(f"ALTER TABLE seen_links ADD COLUMN {coldef}")
        except Exception:
            pass
    conn.commit()
    return conn

def get_seen(conn):
    return {row[0] for row in conn.execute("SELECT url FROM seen_links")}

def get_row(conn, url):
    cur = conn.execute("SELECT url, last_title FROM seen_links WHERE url=?", (url,))
    row = cur.fetchone()
    if not row:
        return None
    return {"url": row[0], "last_title": row[1]}

def set_title(conn, url, title):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE seen_links SET last_title=?, last_changed_utc=? WHERE url=?", (title, now, url))
    conn.commit()

def mark_seen(conn, items):
    """
    items: list of (url, title)
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("""
        INSERT OR IGNORE INTO seen_links(url, first_seen_utc, last_title, last_changed_utc)
        VALUES(?,?,?,?)
    """, [(u, now, t, None) for (u, t) in items])
    conn.commit()

# ---------- Scrape + notify ----------

def fetch_links():
    r = requests.get(BASE_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not ALLOWED_HREF.search(href):
            continue
        url = urljoin(BASE_URL, href)
        text = " ".join(a.get_text(strip=True).split())
        links.append((url, text))

    # De-duplicate by URL
    seen_urls = set()
    uniq = []
    for url, text in links:
        if url not in seen_urls:
            seen_urls.add(url)
            uniq.append((url, text))
    return uniq

def send_to_webhook(webhook_url, message, url):
    payload = {"content": f"{message}\n{url}"}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR sending to Discord ({webhook_url[:60]}...): {e}")

def send_discord(webhooks, message, url):
    """
    webhooks: list of {"url": str, "prefix": str}
    """
    if not webhooks:
        print("⚠️  No Discord webhooks configured. Printing message instead:")
        print(f"{message}\n{url}")
        return
    for w in webhooks:
        if isinstance(w, dict):
            prefix = w.get("prefix", "")
            u = w.get("url")
            if u:
                send_to_webhook(u, f"{prefix}{message}", url)
        elif isinstance(w, str):
            # tolerate plain string entries
            send_to_webhook(w, message, url)

# ---------- Main ----------

def main():
    cfg = load_config()
    webhooks = cfg.get("DISCORD_WEBHOOK_URLS", [])

    conn = init_db()
    previously_seen = get_seen(conn)

    try:
        items = fetch_links()  # list[(url, title)]
    except Exception as e:
        print(f"ERROR fetching {BASE_URL}: {e}")
        return 1

    # 1) New URLs
    new_items = [(u, t) for (u, t) in items if u not in previously_seen]
    if new_items:
        for url, title in new_items:
            send_discord(webhooks, f"🆕 NEW: **{title}**", url)
        mark_seen(conn, new_items)

    # 2) Title updates on listing page
    updated_count = 0
    for url, title in items:
        if url not in previously_seen:
            continue
        row = get_row(conn, url)
        if not row:
            continue
        last_title = row["last_title"]
        if not last_title:
            # Backfill title (DB from earlier version)
            set_title(conn, url, title)
        elif title != last_title:
            send_discord(webhooks, f"🔄 UPDATED (title changed): **{title}**", url)
            set_title(conn, url, title)
            updated_count += 1

    if not new_items and updated_count == 0:
        print(f"{datetime.now()}: No new links. No title updates detected.")
    else:
        print(f"{datetime.now()}: New links: {len(new_items)}, Title updates: {updated_count}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
