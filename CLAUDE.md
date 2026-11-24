# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal Python tool that runs on the owner's Windows PC each morning and builds one HTML page: today's
Google Calendar, unread Gmail, PC updates (Chrome / winget / Windows Update), and unseen news headlines from
RSS feeds. It can also email that page to the owner's own Gmail (`email_me` in `settings.json`). No AI and no paid services.

## Commands

    python -m pip install -r requirements.txt    # Google libs + pytest (news/updates need only the stdlib)
    python -m pytest                             # all tests (fakes only; no network, Google, or PC calls)
    python -m pytest tests/test_brief.py::test_full_run_with_fakes   # one test
    python -m brief.main [--no-open | --setup-google]                # what the `brief` launcher runs

`brief --no-open` is what the morning schedule runs. `--setup-google` is the only path that may open a browser for OAuth.

## Architecture

`brief/main.py` is the entry point: `run()` → `gather()` → `render.build_page()` → `save_page()` → `email_page()` → `RunLog.finish()`.

- **Sections fail independently.** `gather()` wraps Google, each PC check, and each news feed in its own
  try/except. A failure becomes a message shown in that section of the page and an entry in the run log; it
  never stops the page. Keep this property when adding sections. Only an exception outside those blocks makes the
  run `failed`.
- **Dependency injection for tests.** `gather(..., google=, pc=, fetcher=)` and `run(**fakes)` accept fakes;
  `updates.winget_upgrades(run=)` / `windows_updates(run=)` accept a fake `subprocess.run`. New external calls
  should follow the same pattern so tests never touch real accounts, the PC, or the internet.
- **Code vs. data split** (`config.py`): code lives in OneDrive; private data (Google client secret + token,
  saved pages, `state/seen.json`, `logs/runs.jsonl`) lives in `%LOCALAPPDATA%\morning-brief\` (override with
  `MORNING_BRIEF_DATA`). Never write secrets or state into the repo folder.
- **Google** (`google_data.py`): scopes are `gmail.readonly`, `gmail.send` (only ever to the user's own address),
  `calendar.readonly`. The daily run uses `interactive=False` and raises `NotSetUp` instead of opening a browser;
  `NotSetUp` is expected and is shown on the page, not logged as an error. Google libs are imported lazily so
  the rest works without them.
- **News** (`news.py`, `feeds.py`, `seen.py`): feeds per section from `settings.json`; already-shown IDs are
  filtered via `SeenStore`, feeds are round-robin interleaved so one site can't dominate, capped at
  `news_per_section`. `seen.json` is saved atomically (tmp + replace).
- **Updates** (`updates.py`): read-only; each check returns `None` on non-Windows. The Chrome "latest" is the
  newest version with rollout fraction ≥ `ROLLOUT_THRESHOLD` (0.5), not the newest 1% early-rollout build.
  winget output parsing (`parse_winget_table`) is tested against real captured output, spinner characters included.
- **Rendering** (`render.py`): all outside text goes through `esc()` and URLs through `safe_url()`. Keep that
  for any new content (there's a test for escaping and bad links).
- **Run log** (`runlog.py`): one JSON line per run in `logs/runs.jsonl` with status `ok` / `ok_with_errors` /
  `failed`, counts, and errors. A future supervisor agent reads this format, so keep it stable.

`settings.json` holds the user-editable settings (feeds, headline count, Gmail query, name, `keep_pages`, `email_me`).
The Gmail query excludes the brief's own emails (`-subject:"Morning brief"`).

`docs/` is a static site (home, privacy policy, terms) for the Google OAuth consent screen. It isn't part of the program.

## Style

The owner isn't a professional developer. The code uses plain-language docstrings and comments that explain
*why* something is done (e.g. why versions are compared as tuples). Match that tone, and keep
user-facing messages actionable, e.g. "Run: brief --setup-google".
