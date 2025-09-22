
=============================
MapleSEA Updates → Discord Bot
=============================

This small tool checks https://www.maplesea.com/updates for NEW links and posts them to your Discord channel via a webhook.

You have two easy ways to run it:
1) **GitHub Actions (recommended — no server needed)**
2) **Your own computer (Windows/Mac/Linux)**

---------------------------------------
Before you start: Create a Discord webhook
---------------------------------------
1. In Discord, open your server where you have permission to add integrations.
2. Go to **Server Settings → Integrations → Webhooks**.
3. Click **New Webhook** → choose a channel (where messages will be posted) → **Copy Webhook URL**.
4. Keep this URL safe. You will paste it below as `DISCORD_WEBHOOK_URL`.

=================================
Option 1: Run with GitHub Actions
=================================

This is "serverless"—GitHub will run the watcher every 15 minutes for you.

A) Create a new (or use an existing) repository on GitHub.
B) Download the four bot files from this folder:
   - `maplesea_updates_watcher.py`
   - `config.example.json` (for reference)
   - `.github/workflows/maple-watcher.yml`
   - `README_MapleSEA_Watcher.txt` (this file)

C) Add them to your repo and push.

D) Add your webhook as a **Secret**:
   1. Go to your GitHub repository page.
   2. Click **Settings** → **Secrets and variables** → **Actions**.
   3. Click **New repository secret**.
   4. Name: `DISCORD_WEBHOOK_URL`
      Value: Paste your webhook URL from Discord.
   5. Save.

E) GitHub will now run your workflow every 15 minutes.
   - To test immediately: go to **Actions** tab → open "MapleSEA Updates Watcher" → **Run workflow**.

Notes:
- The workflow caches `seen_links.db` so it remembers what it's already posted.
- To reset memory, delete the cached file in your repo or change the cache key in the workflow.

====================================
Option 2: Run on your own computer
====================================

A) Install Python (if you don't have it yet)
   - Windows: https://www.python.org/downloads/windows/ (check the box "Add Python to PATH" during install)
   - macOS: Python 3 usually exists, but you can also install from https://www.python.org/downloads/macos/
   - Linux: Use your package manager (e.g., `sudo apt-get install python3 python3-pip`).

B) Download these two files to a single folder (e.g., `C:\maple_bot` on Windows, or `~/maple_bot` on Mac/Linux):
   - `maplesea_updates_watcher.py`
   - `config.example.json` → rename it to **`config.json`**

C) Open the `config.json` file in a text editor and paste your Discord webhook URL like this:
   {
     "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/XXXXXXXX"
   }
   Save.

D) Open a terminal in that folder and install the two dependencies:
   Windows (PowerShell):
     python -m pip install requests beautifulsoup4

   macOS/Linux (Terminal):
     python3 -m pip install requests beautifulsoup4

E) First manual run (to verify everything works):
   Windows:
     python maplesea_updates_watcher.py

   macOS/Linux:
     python3 maplesea_updates_watcher.py

   You should see either "No new links." or a message that it posted new links to Discord.

F) Schedule it to run automatically every 10–15 minutes:

   • Windows Task Scheduler
     1. Open **Task Scheduler**.
     2. Action → **Create Task…**
     3. General: Name it "MapleSEA Watcher".
     4. Triggers tab → **New…** → set "Daily", Repeat task every: 15 minutes, for a duration of: Indefinitely.
     5. Actions tab → **New…**
        - Program/script:  python
        - Add arguments:   maplesea_updates_watcher.py
        - Start in:        (the folder where the script is located, e.g., C:\maple_bot)
     6. OK to save. Right-click the task → **Run** to test.

   • macOS/Linux (cron)
     1. Open terminal and run:  crontab -e
     2. Add this line (every 15 minutes):
        */15 * * * * /usr/bin/python3 /FULL/PATH/TO/maplesea_updates_watcher.py >> /tmp/maple_watcher.log 2>&1
     3. Save and exit. Check /tmp/maple_watcher.log to see output.

------------------------
How the bot detects news
------------------------
- It loads https://www.maplesea.com/updates and extracts all links that look like update pages.
- It keeps a small database file `seen_links.db` in the same folder to remember what was already posted.
- If the site ever changes its structure dramatically, tell the assistant and we’ll adjust the selector.

----------------
Troubleshooting
----------------
• "Module not found" (e.g., requests or bs4): Install dependencies again with pip as shown above.
• No messages in Discord:
  - Confirm your webhook is correct in `config.json`.
  - Run the script manually to see output.
• Reset memory: delete `seen_links.db` (you will be notified again about all currently visible links).
• Be polite: don't schedule more frequent than every 5–10 minutes.

Enjoy!
