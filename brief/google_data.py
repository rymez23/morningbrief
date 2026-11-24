"""
EMAIL + CALENDAR SECTIONS: reads Gmail and Google Calendar, and emails the
finished brief to you.

Permissions requested ("scopes"):
  gmail.readonly     read email (cannot delete, archive, or change anything)
  gmail.send         send email; the code below only ever sends to YOUR OWN
                     address, which it asks Google for (see send_brief)
  calendar.readonly  read events (cannot add, change, or delete)

How sign-in works (OAuth):
  1. You create a free "OAuth client" in Google Cloud and download its key file.
     Save it as  google_client_secret.json  in the data folder (see config.py).
  2. Run  brief --setup-google  once. A browser window asks you to approve
     read-only access. Google then gives us a token, saved as google_token.json.
  3. Every morning the script uses that token. It never needs your password.

Keep both files private. They stay in the local data folder, not in OneDrive.
Delete google_token.json to sign out.

The Google libraries are only needed for this section. Without them (or without
the key file), the page simply says how to set it up; everything else still works.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]
SECRET_FILE = "google_client_secret.json"
TOKEN_FILE = "google_token.json"


class NotSetUp(Exception):
    """Google isn't connected yet (or the sign-in expired). The message says what to do."""


# ---------------------------------------------------------------- sign-in

def load_credentials(data: Path, interactive: bool = False):
    """Return working Google credentials.

    interactive=False (the daily run): never opens a browser. If sign-in is needed,
    raise NotSetUp so the page can show instructions instead of hanging.
    interactive=True (brief --setup-google): opens the browser approval page.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise NotSetUp("Google libraries not installed. Run: python -m pip install -r requirements.txt")

    secret, token = data / SECRET_FILE, data / TOKEN_FILE
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())                 # quietly get a fresh token
            token.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            if not interactive:
                raise NotSetUp(f"Google sign-in expired ({e}). Run: brief --setup-google")

    if not interactive:
        raise NotSetUp("Google not connected yet. Run: brief --setup-google")
    if not secret.exists():
        import_key_from_downloads(secret)

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0)            # opens your browser to approve
    data.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def import_key_from_downloads(secret: Path, downloads: Path | None = None) -> None:
    """Google names the key file 'client_secret_<long id>.json' and your browser
    saves it to Downloads. Find the newest one there and MOVE it into the private
    data folder, so it doesn't sit in Downloads where other apps can see it."""
    import shutil
    downloads = downloads or Path.home() / "Downloads"
    found = sorted(downloads.glob("client_secret*.json"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise NotSetUp(f"Key file not found. Download it from Google Cloud into {downloads}, "
                       f"or save it as {secret}")
    secret.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(found[-1]), secret)
    print(f"Moved key file {found[-1].name} to {secret}")


def build_services(creds):
    from googleapiclient.discovery import build
    return (build("gmail", "v1", credentials=creds, cache_discovery=False),
            build("calendar", "v3", credentials=creds, cache_discovery=False))


# ---------------------------------------------------------------- Gmail

def parse_message(msg: dict) -> dict:
    """Turn Gmail's raw message JSON into {from, subject, snippet, link}."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender = headers.get("from", "")
    if "<" in sender:                                # 'Jane Doe <jane@x.com>' -> 'Jane Doe'
        sender = sender.split("<")[0].strip().strip('"') or sender
    return {
        "from": sender,
        "subject": headers.get("subject", "(no subject)"),
        "snippet": msg.get("snippet", ""),
        "link": f"https://mail.google.com/mail/u/0/#inbox/{msg.get('threadId', msg.get('id', ''))}",
    }


def unread_email(gmail, query: str, limit: int) -> list[dict]:
    """Unread inbox mail matching `query` (same syntax as the Gmail search box)."""
    found = gmail.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    out = []
    for ref in found.get("messages", []):
        # format="metadata" fetches only headers + snippet, not the whole email
        msg = gmail.users().messages().get(userId="me", id=ref["id"], format="metadata",
                                           metadataHeaders=["From", "Subject"]).execute()
        out.append(parse_message(msg))
    return out


# ---------------------------------------------------------------- Calendar

def parse_event(ev: dict, calendar_name: str) -> dict:
    """Turn a Calendar API event into {time, title, location, link, calendar, sort}.

    All-day events have start.date ('2026-11-24'); timed events have
    start.dateTime ('2026-11-24T09:30:00-07:00').
    """
    start = ev.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        label = dt.strftime("%I:%M %p").lstrip("0")  # '9:30 AM'
        sort = dt.isoformat()
    else:
        label, sort = "All day", "0"                 # all-day events sort first
    return {
        "time": label,
        "title": ev.get("summary", "(no title)"),
        "location": ev.get("location", ""),
        "link": ev.get("htmlLink", ""),
        "calendar": calendar_name,
        "sort": sort,
    }


def todays_events(calendar, now: datetime | None = None) -> list[dict]:
    """Events from midnight to midnight today, from every calendar you have ticked in Google Calendar."""
    now = (now or datetime.now()).astimezone()       # local time with your time-zone offset
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    events = []
    for cal in calendar.calendarList().list().execute().get("items", []):
        if not cal.get("selected", False):
            continue                                  # calendars you've hidden in Google Calendar
        resp = calendar.events().list(
            calendarId=cal["id"], timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True,                        # expand repeating events into today's copy
            orderBy="startTime").execute()
        name = cal.get("summaryOverride") or cal.get("summary", "")
        events += [parse_event(ev, name) for ev in resp.get("items", [])
                   if ev.get("status") != "cancelled"]
    return sorted(events, key=lambda e: e["sort"])


# ---------------------------------------------------------------- email the brief to yourself

def build_email(to: str, subject: str, html_body: str, text_body: str) -> dict:
    """Package the page as an email in the format Gmail's API expects.

    The email has two versions ("multipart/alternative"): the HTML page, and a
    plain-text fallback for apps that can't show HTML. Gmail's API wants the
    whole email base64url-encoded in a field called "raw".
    """
    import base64
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_brief(gmail, subject: str, html_body: str, text_body: str) -> str:
    """Email the brief to the signed-in account's own address. Returns that address.

    The recipient is NOT a setting: it is always the address Google says you are
    signed in as, so this code can't be used to send mail to anyone else.
    """
    me = gmail.users().getProfile(userId="me").execute()["emailAddress"]
    gmail.users().messages().send(userId="me", body=build_email(me, subject, html_body, text_body)).execute()
    return me
