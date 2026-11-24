"""
Tests for the morning brief. Run with:   python -m pytest

Everything outside the program (Google, your PC, news sites) is replaced by
fakes, so the tests are fast, free, and never touch your real accounts.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

from brief import google_data, news, render, updates
from brief.feeds import Item
from brief.main import run
from brief.seen import SeenStore

PROJECT = Path(__file__).resolve().parent.parent

# Real output captured from `winget upgrade` on PJ's PC (spinner characters included)
WINGET = """\r   - \r   \\ \r
Name                                                         Id                           Version              Available            Source
------------------------------------------------------------------------------------------------------------------------------------------
Git                                                          Git.Git                      2.56.0.3             2.56.1               winget
Microsoft Teams                                              Microsoft.Teams              25044.2208.3471.2155 26288.2004.5269.3420 winget
2 upgrades available.
"""


def item(n, source="Feed A", section="Tech"):
    return Item(id=f"{source}-{n}", source=source, topic=section, title=f"Story {n}",
                link=f"https://example.com/{n}", summary="summary")


# ---------------------------------------------------------------- updates.py

def test_parse_winget_table():
    rows = updates.parse_winget_table(WINGET)
    assert rows == [
        {"name": "Git", "id": "Git.Git", "current": "2.56.0.3", "available": "2.56.1"},
        {"name": "Microsoft Teams", "id": "Microsoft.Teams",
         "current": "25044.2208.3471.2155", "available": "26288.2004.5269.3420"},
    ]


def test_winget_no_updates_returns_empty_list():
    assert updates.parse_winget_table("No installed package found matching input criteria.") == []


def test_chrome_versions_compare_as_numbers():
    assert updates.chrome_status("158.0.8127.37", "159.0.8154.13")["up_to_date"] is False
    assert updates.chrome_status("159.0.8154.13", "159.0.8154.13")["up_to_date"] is True
    assert updates.version_tuple("99.0") < updates.version_tuple("158.0")   # text compare would say the opposite


def test_windows_update_single_result_is_a_list():
    fake = lambda *a, **k: NS(returncode=0, stdout='"Defender update KB2267602"', stderr="")
    updates.IS_WINDOWS, saved = True, updates.IS_WINDOWS
    try:
        assert updates.windows_updates(run=fake) == ["Defender update KB2267602"]
    finally:
        updates.IS_WINDOWS = saved


# ---------------------------------------------------------------- news.py

def test_news_interleaves_caps_and_skips_seen(tmp_path):
    seen = SeenStore(tmp_path / "seen.json")
    settings = {"news_per_section": 3,
                "news": {"Tech": [{"name": "Feed A", "url": "a"}, {"name": "Feed B", "url": "b"}]}}
    feeds = {"Feed A": [item(1, "Feed A"), item(2, "Feed A")], "Feed B": [item(1, "Feed B")]}
    fetch = lambda src: feeds[src["name"]]

    sections, errors = news.gather_news(settings, seen, fetch)
    assert [i.id for i in sections["Tech"]] == ["Feed A-1", "Feed B-1", "Feed A-2"]

    sections, _ = news.gather_news(settings, seen, fetch)       # next morning, same stories
    assert sections["Tech"] == []


def test_news_broken_feed_reported(tmp_path):
    def fetch(src):
        raise ConnectionError("down")
    sections, errors = news.gather_news(
        {"news": {"Tech": [{"name": "X", "url": "x"}]}}, SeenStore(tmp_path / "s.json"), fetch)
    assert sections["Tech"] == [] and errors == ["X: down"]


# ---------------------------------------------------------------- google_data.py

def test_parse_gmail_message():
    msg = {"id": "m1", "threadId": "t1", "snippet": "Your package shipped",
           "payload": {"headers": [{"name": "From", "value": '"Amazon" <ship@amazon.com>'},
                                   {"name": "Subject", "value": "Shipped!"}]}}
    assert google_data.parse_message(msg) == {
        "from": "Amazon", "subject": "Shipped!", "snippet": "Your package shipped",
        "link": "https://mail.google.com/mail/u/0/#inbox/t1"}


def test_parse_events_timed_and_all_day():
    timed = google_data.parse_event({"summary": "Shift", "start": {"dateTime": "2026-11-24T06:30:00-07:00"}}, "Work")
    allday = google_data.parse_event({"summary": "Holiday", "start": {"date": "2026-11-24"}}, "Home")
    assert timed["time"] == "6:30 AM" and allday["time"] == "All day"
    assert sorted([timed, allday], key=lambda e: e["sort"])[0] is allday


def test_daily_run_never_opens_browser_when_not_set_up(tmp_path):
    try:
        google_data.load_credentials(tmp_path, interactive=False)
        assert False, "should have raised NotSetUp"
    except google_data.NotSetUp as e:
        assert "brief --setup-google" in str(e) or "pip install" in str(e)


# ---------------------------------------------------------------- render.py

def test_page_escapes_outside_text_and_blocks_bad_links():
    evil = Item(id="x", source="Bad", topic="Tech", title="<script>alert(1)</script>",
                link="javascript:alert(1)", summary="<img src=x onerror=alert(1)>")
    d = {"name": "PJ", "events": [], "emails": [], "google_problem": "", "chrome": None,
         "apps": None, "windows": None, "update_problems": [], "news": {"Tech": [evil]},
         "news_problems": []}
    page = render.build_page(d, datetime(2026, 11, 24, 5, 30))
    assert "<script>alert" not in page and "<img src=x" not in page
    assert 'href="#"' in page and "javascript:" not in page
    assert "Good morning, PJ" in page


# ---------------------------------------------------------------- main.py (everything together)

class FakeRequest:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


def fake_google():
    msg = {"id": "m1", "threadId": "t1", "snippet": "hi",
           "payload": {"headers": [{"name": "From", "value": "Mom"}, {"name": "Subject", "value": "Dinner?"}]}}
    sent = []                                    # records every email "sent"
    messages = NS(list=lambda **k: FakeRequest({"messages": [{"id": "m1"}]}),
                  get=lambda **k: FakeRequest(msg),
                  send=lambda **k: sent.append(k) or FakeRequest({"id": "s1"}))
    users = NS(messages=lambda: messages,
               getProfile=lambda **k: FakeRequest({"emailAddress": "pj@example.com"}))
    gmail = NS(users=lambda: users, sent=sent)
    calendar = NS(
        calendarList=lambda: NS(list=lambda: FakeRequest({"items": [
            {"id": "primary", "summary": "PJ", "selected": True},
            {"id": "hidden", "summary": "Hidden", "selected": False}]})),
        events=lambda: NS(list=lambda **k: FakeRequest({"items": [
            {"summary": "Shift", "start": {"dateTime": "2026-11-24T06:30:00-07:00"}, "htmlLink": "https://calendar.google.com/x"}]})))
    return gmail, calendar


def test_full_run_with_fakes(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    shutil.copy(PROJECT / "settings.json", root / "settings.json")
    pc = {"chrome": lambda: {"installed": "158.0", "latest": "159.0", "up_to_date": False},
          "apps": lambda: updates.parse_winget_table(WINGET),
          "windows": lambda: (_ for _ in ()).throw(RuntimeError("service busy"))}

    google = fake_google()
    rec = run(open_page=False, root=root, data=tmp_path / "data",
              google=google, pc=pc, fetcher=lambda src: [item(1, src["name"], src["topic"])])

    assert rec["status"] == "ok_with_errors"                     # Windows check failed on purpose
    assert rec["counts"] == {"events": 1, "emails": 1, "news": 9, "app_updates": 2,
                             "windows_updates": 0, "emailed": 1}
    (sent,) = google[0].sent                          # exactly one email went out...
    import base64, email
    mail = email.message_from_bytes(base64.urlsafe_b64decode(sent["body"]["raw"]))
    assert mail["To"] == "pj@example.com"            # ...to the signed-in account only
    assert mail["Subject"].startswith("Morning brief")
    page = Path(rec["page"]).read_text(encoding="utf-8")
    for expected in ("Shift", "Dinner?", "Chrome update available", "winget upgrade --all",
                     "Windows Update check failed", "Tech news", "Politics news", "Science news"):
        assert expected in page
    assert (tmp_path / "data" / "pages" / "latest.html").exists()


def test_old_pages_are_cleaned_up(tmp_path):
    from brief.main import save_page
    pages = tmp_path / "pages"
    pages.mkdir()
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        (pages / f"{day}.html").write_text("old")
    save_page("new", tmp_path, keep=2)
    assert len(list(pages.glob("????-??-??.html"))) == 2


def test_email_skipped_when_google_not_connected(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    shutil.copy(PROJECT / "settings.json", root / "settings.json")
    pc = {"chrome": lambda: None, "apps": lambda: [], "windows": lambda: []}
    # google=None and no key file -> NotSetUp -> page still made, email logged as not sent
    rec = run(open_page=False, root=root, data=tmp_path / "data", pc=pc, fetcher=lambda src: [])
    assert rec["status"] == "ok_with_errors"
    assert rec["errors"] == [{"where": "email", "error": "Not sent: Google isn't connected"}]


def test_key_file_moved_from_downloads(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "client_secret_123.apps.googleusercontent.com.json").write_text("{}")
    secret = tmp_path / "data" / google_data.SECRET_FILE
    google_data.import_key_from_downloads(secret, downloads)
    assert secret.exists() and not list(downloads.glob("client_secret*.json"))
