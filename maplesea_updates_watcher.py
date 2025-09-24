#!/usr/bin/env python3
"""
MapleSEA Updates Watcher
- Checks https://www.maplesea.com/updates for new update links
- Notifies a Discord channel via webhook when new links appear
- Also detects if an existing link's headline (title) on the listing page changes
- Stores "seen" links & last known title in a tiny SQLite database

Setup:
1) Put your Discord webhook URL into config.json (same folder as this script), e.g.:
   { "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/XXXX" }
2) Run once manually; then your GitHub Actions schedule will handle the rest.
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
    "User-Agent": "MapleSEA-Updates-Watcher/1.1 (contact: example@example.com)"
}
TIMEOUT = 20

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"WARNING: Could not read {CONFIG_PATH}: {e}")
    if not cfg.get("DISCORD_WEBHOOK_URL"):
        env_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if env_url:
            cfg["DISCORD_WEBHOOK_URL"] = env_url
    return cfg

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
    # Safe no-ops if columns already exist:
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

def send_discord(webhook_url, url, title_or_message):
    if not webhook_url:
        print("⚠️  DISCORD_WEBHOOK_URL not set. Please fill config.json.")
        print(f"[MSG] {title_or_message}\n{url}")
        return
    payload = {"content": f"{title_or_message}\n{url}"}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR sending to Discord: {e}")

def main():
    cfg = load_config()
    webhook = cfg.get("DISCORD_WEBHOOK_URL")

    conn = init_db()
    previously_seen = get_seen(conn)

    try:
        items = fetch_links()  # list[(url, title)] newest-first on MapleSEA
    except Exception as e:
        print(f"ERROR fetching {BASE_URL}: {e}")
        return 1

    # 1) Handle brand-new URLs
    new_items = [(u, t) for (u, t) in items if u not in previously_seen]
    if new_items:
        for url, title in new_items:
            send_discord(webhook, url, f"🆕 NEW: **{title}**")
        mark_seen(conn, new_items)

    # 2) Handle UPDATED titles on the listing page
    updated_count = 0
    for url, title in items:
        if url not in previously_seen:
            continue  # just handled above
        row = get_row(conn, url)
        if not row:
            continue
        last_title = row["last_title"]
        if not last_title:
            # Backfill without notifying (first time migrating old DB rows)
            set_title(conn, url, title)
        elif title != last_title:
            send_discord(webhook, url, f"🔄 UPDATED (title changed): **{title}**")
            set_title(conn, url, title)
            updated_count += 1

    if not new_items and updated_count == 0:
        print(f"{datetime.now()}: No new links. No title updates detected.")
    else:
        print(f"{datetime.now()}: New links: {len(new_items)}, Title updates: {updated_count}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
