"""
The entry point. Gathers everything, builds the page, opens it in your browser.

    1. google_data.py  today's calendar + unread email   (read-only)
    2. updates.py      Chrome, Windows Update, app updates (read-only)
    3. news.py         new Tech / Politics / Science headlines
    4. render.py       build one HTML page and save it
    5. google_data.py  email the page to yourself (if "email_me" is true in settings.json)
    6. runlog.py       append a one-line report to the log (for the future supervisor)

Every section is independent: if one breaks (site down, Google not set up yet),
the page still appears and shows what went wrong in that section.

Commands (the "brief" launcher runs this file):
    brief                 make today's page and open it
    brief --no-open       make the page but don't open it
    brief --setup-google  one-time: connect Gmail + Calendar (opens a browser)
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path

from . import google_data, news, updates
from .config import CODE_ROOT, data_dir, load_settings
from .render import build_page
from .runlog import RunLog
from .seen import SeenStore


def gather(settings: dict, data: Path, log: RunLog, google=None, pc=None, fetcher=None) -> dict:
    """Collect every section's data into one dict for render.build_page().

    google / pc / fetcher let the tests swap in fakes instead of the real
    Google account, the real PC, and the real internet.
    """
    d = {"name": settings.get("name", ""), "_gmail": None,
         "events": [], "emails": [], "google_problem": "",
         "chrome": None, "apps": None, "windows": None, "update_problems": [],
         "news": {}, "news_problems": []}

    # 1. Google (calendar + email) -------------------------------------------
    try:
        if google is None:
            creds = google_data.load_credentials(data, interactive=False)
            gmail, calendar = google_data.build_services(creds)
        else:
            gmail, calendar = google
        d["_gmail"] = gmail                             # kept so run() can email the page
        d["events"] = google_data.todays_events(calendar)
        g = settings.get("gmail", {})
        d["emails"] = google_data.unread_email(gmail, g.get("query", "in:inbox is:unread"), g.get("max", 15))
    except google_data.NotSetUp as e:
        d["google_problem"] = str(e)                    # expected until setup is done
    except Exception as e:
        d["google_problem"] = f"Couldn't reach Google: {e}"
        log.error("google", e)

    # 2. PC updates (each check separate, so one failure doesn't hide the others)
    pc = pc or {"chrome": updates.chrome_status, "apps": updates.winget_upgrades,
                "windows": updates.windows_updates}
    for key, label in (("chrome", "Chrome check"), ("apps", "App update check"),
                       ("windows", "Windows Update check")):
        try:
            d[key] = pc[key]()
        except Exception as e:
            d["update_problems"].append(f"{label} failed: {e}")
            log.error(f"updates:{key}", e)

    # 3. News --------------------------------------------------------------------
    seen = SeenStore(data / "state" / "seen.json")
    d["news"], d["news_problems"] = news.gather_news(
        settings, seen, **({"fetcher": fetcher} if fetcher else {}))
    for p in d["news_problems"]:
        log.error("news", p)
    seen.save()

    log.count("events", len(d["events"]))
    log.count("emails", len(d["emails"]))
    log.count("news", sum(len(v) for v in d["news"].values()))
    log.count("app_updates", len(d["apps"] or []))
    log.count("windows_updates", len(d["windows"] or []))
    return d


def plain_text(d: dict) -> str:
    """Short text version of the brief, for email apps that can't show the HTML page."""
    lines = [f"{len(d['events'])} events today, {len(d['emails'])} unread emails."]
    lines += [f"{e['time']}  {e['title']}" for e in d["events"]]
    if d["chrome"] and not d["chrome"]["up_to_date"]:
        lines.append(f"Chrome update available: {d['chrome']['latest']}")
    if d["windows"]:
        lines.append(f"{len(d['windows'])} Windows updates pending")
    if d["apps"]:
        lines.append(f"{len(d['apps'])} app updates available")
    for section, items in d["news"].items():
        lines.append(f"\n{section}:")
        lines += [f"- {i.title} ({i.link})" for i in items]
    return "\n".join(lines)


def email_page(d: dict, page: str, settings: dict, log: RunLog, now: datetime) -> None:
    """Send the brief to your own Gmail, so you can read it on your phone."""
    if not settings.get("email_me", False):
        return
    if d["_gmail"] is None:
        log.error("email", "Not sent: Google isn't connected")
        return
    try:
        subject = f"Morning brief · {now.strftime('%a %b %d').replace(' 0', ' ')}"
        to = google_data.send_brief(d["_gmail"], subject, page, plain_text(d))
        log.count("emailed", 1)
        print(f"Emailed to {to}")
    except Exception as e:
        log.error("email", e)
        if "insufficient" in str(e).lower() or "scope" in str(e).lower():
            print("Email failed: Google permission missing. Run: brief --setup-google")


def save_page(page: str, data: Path, keep: int) -> Path:
    """Save as pages/2026-11-24.html (plus latest.html), deleting pages older than `keep`."""
    pages = data / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    path = pages / f"{date.today()}.html"
    path.write_text(page, encoding="utf-8")
    (pages / "latest.html").write_text(page, encoding="utf-8")
    dated = sorted(p for p in pages.glob("????-??-??.html"))   # oldest first (names sort by date)
    for old in dated[:-keep] if keep > 0 else []:
        old.unlink()
    return path


def run(open_page: bool = True, root: Path = CODE_ROOT, data: Path | None = None, **fakes) -> dict:
    data = data or data_dir()
    log = RunLog(data / "logs" / "runs.jsonl", agent="morning-brief")
    try:
        settings = load_settings(root)
        d = gather(settings, data, log, **fakes)
        now = datetime.now()
        page = build_page(d, now)
        path = save_page(page, data, settings.get("keep_pages", 14))
    except Exception as e:
        log.error("run", e)
        print(f"Brief failed: {e}")
        return log.finish("failed")

    print(f"Brief saved: {path}")
    email_page(d, page, settings, log, now)       # a failed email is logged, not fatal
    if open_page:
        webbrowser.open(path.as_uri())    # opens in your default browser
    rec = log.finish("ok")
    rec["page"] = str(path)
    return rec


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Your morning brief: calendar, email, PC updates, news.")
    parser.add_argument("--no-open", action="store_true", help="save the page without opening it")
    parser.add_argument("--setup-google", action="store_true",
                        help="one-time: connect Gmail and Calendar (read-only)")
    args = parser.parse_args(argv)

    if args.setup_google:
        try:
            google_data.load_credentials(data_dir(), interactive=True)
            print("Google connected. Run 'brief' to see your email and calendar.")
            return 0
        except google_data.NotSetUp as e:
            print(e)
            return 1

    rec = run(open_page=not args.no_open)
    print(f"Run {rec['run_id']}: {rec['status']}"
          + (f" ({len(rec['errors'])} problem(s), see the page)" if rec["errors"] else ""))
    return 1 if rec["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
