#!/usr/bin/env python3
"""
MapleSEA Updates Watcher
- Checks https://www.maplesea.com/updates for new update links
- Notifies a Discord channel via webhook when new links appear
- Stores "seen" links in a tiny SQLite database

Setup (non-coder friendly):
1) Put your Discord webhook URL into config.json (same folder as this script).
2) Run:  python maplesea_updates_watcher.py
3) Schedule it (Windows Task Scheduler or cron) to run every 10–15 minutes.
"""
import os, sqlite3, time, re, json
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.maplesea.com/updates"
ALLOWED_HREF = re.compile(r"/updates(/|$)", re.IGNORECASE)
DB_PATH = os.environ.get("DB_PATH", "seen_links.db")
CONFIG_PATH = "config.json"

HEADERS = {
    "User-Agent": "MapleSEA-Updates-Watcher/1.0 (contact: example@example.com)"
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
    # Fallback to environment variable if no config.json
    if not cfg.get("DISCORD_WEBHOOK_URL"):
        env_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if env_url:
            cfg["DISCORD_WEBHOOK_URL"] = env_url
    return cfg

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_links (
            url TEXT PRIMARY KEY,
            first_seen_utc TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def get_seen(conn):
    return {row[0] for row in conn.execute("SELECT url FROM seen_links")}

def mark_seen(conn, urls):
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("INSERT OR IGNORE INTO seen_links(url, first_seen_utc) VALUES(?,?)",
                     [(u, now) for u in urls])
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

def send_discord(webhook_url, url, title=None):
    if not webhook_url:
        print("⚠️  DISCORD_WEBHOOK_URL not set. Please fill config.json.")
        print(f"[NEW UPDATE] {title or url}\n{url}")
        return

    content = f"🆕 MapleSEA update:\n**{title or url}**\n{url}"
    payload = {"content": content}
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
        items = fetch_links()
    except Exception as e:
        print(f"ERROR fetching {BASE_URL}: {e}")
        return 1

    new_items = [(u, t) for (u, t) in items if u not in previously_seen]
    if new_items:
        for url, title in new_items:
            send_discord(webhook, url, title)
        mark_seen(conn, [u for (u, _) in new_items])
        print(f"{datetime.now()}: Posted {len(new_items)} new link(s).")
    else:
        print(f"{datetime.now()}: No new links.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
