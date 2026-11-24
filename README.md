# Morning Brief

One page each morning with what you need to know before your day starts:

- **Today's calendar** and **unread email** (Gmail, read-only)
- **Your PC**: Chrome version, pending Windows updates, app updates (read-only; nothing is installed)
- **News**: new Tech, Politics and Science headlines you haven't seen yet

No AI and no paid services. Each section works on its own: if one breaks, the page still
appears and says what went wrong.

## Commands

    brief                  make today's page and open it in your browser
    brief --no-open        make the page without opening it (used by the morning schedule)
    brief --setup-google   one-time: connect Gmail + Calendar

## Where things are

| What | Where |
|---|---|
| Code (this folder) | `OneDrive\Documents\morning-brief` |
| Settings you can edit | `settings.json` here: news sites, headline count, Gmail search, your name |
| Saved pages | `%LOCALAPPDATA%\morning-brief\pages\` (`latest.html` is always today's) |
| Google key + sign-in token | `%LOCALAPPDATA%\morning-brief\` (on this PC only, never synced) |
| Run log for the future supervisor | `%LOCALAPPDATA%\morning-brief\logs\runs.jsonl` |

## How the code is organized (start reading at main.py)

| File | Job |
|---|---|
| `brief/main.py` | Runs every section in order, saves and opens the page |
| `brief/google_data.py` | Read-only Gmail + Calendar, and the one-time sign-in |
| `brief/updates.py` | Chrome, winget (apps) and Windows Update checks |
| `brief/news.py` | Picks new headlines per section, mixing sources |
| `brief/feeds.py` | Downloads and reads RSS/Atom feeds |
| `brief/seen.py` | Remembers which headlines were already shown |
| `brief/render.py` | Builds the HTML page (escapes all outside text for safety) |
| `brief/runlog.py` | One-line report per run |
| `brief/config.py` | Where data is stored |
| `tests/` | `python -m pytest` checks everything with fake data |
