"""
Builds the briefing web page: one self-contained HTML file (no internet needed to view it).

SECURITY NOTE: headlines and email subjects come from outside sources. Every bit
of outside text goes through esc(), so it shows as text and can never run as
code on the page. Links go through safe_url(), which only allows http/https, so
a feed can't sneak in a "javascript:" link.
"""
from __future__ import annotations

import html
from datetime import datetime


def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def safe_url(url: str) -> str:
    url = (url or "").strip()
    return esc(url) if url.lower().startswith(("https://", "http://")) else "#"


def link(text: str, url: str) -> str:
    return f'<a href="{safe_url(url)}" target="_blank" rel="noopener">{esc(text)}</a>'


def section(title: str, body: str, note: str = "") -> str:
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    return f'<section><h2>{esc(title)}</h2>{note_html}{body}</section>'


def empty(msg: str) -> str:
    return f'<p class="muted">{esc(msg)}</p>'


# ---------------------------------------------------------------- the sections

def calendar_html(events, problem):
    if problem:
        return section("Today's calendar", empty(problem))
    if not events:
        return section("Today's calendar", empty("Nothing scheduled today."))
    rows = "".join(
        f'<li><span class="time">{esc(e["time"])}</span> {link(e["title"], e["link"])}'
        f'{" · " + esc(e["location"]) if e["location"] else ""}'
        f' <span class="muted">({esc(e["calendar"])})</span></li>' for e in events)
    return section("Today's calendar", f"<ul>{rows}</ul>")


def email_html(emails, problem):
    title = f"Unread email ({len(emails)})" if emails else "Unread email"
    if problem:
        return section("Unread email", empty(problem))
    if not emails:
        return section(title, empty("Inbox zero. Nothing new."))
    rows = "".join(
        f'<li><b>{esc(m["from"])}</b>: {link(m["subject"], m["link"])}'
        f'<div class="muted small">{esc(m["snippet"][:140])}</div></li>' for m in emails)
    return section(title, f"<ul>{rows}</ul>")


def updates_html(chrome, apps, windows, problems):
    parts = []
    if chrome:
        if chrome["up_to_date"]:
            parts.append(f'<li class="ok">Chrome {esc(chrome["installed"])} is up to date.</li>')
        else:
            parts.append(f'<li class="warn">Chrome update available: {esc(chrome["installed"])} → '
                         f'{esc(chrome["latest"])}. Open Chrome › Settings › About Chrome to update.</li>')
    if windows:
        items = "".join(f"<li>{esc(t)}</li>" for t in windows)
        parts.append(f'<li class="warn">Windows Update: {len(windows)} pending '
                     f'(Settings › Windows Update)<ul>{items}</ul></li>')
    elif windows is not None:
        parts.append('<li class="ok">Windows is up to date.</li>')
    if apps:
        items = "".join(f'<li>{esc(a["name"])}: {esc(a["current"])} → {esc(a["available"])}</li>'
                        for a in apps)
        parts.append(f'<li class="warn">{len(apps)} app updates. To install all, run '
                     f'<code>winget upgrade --all</code><ul>{items}</ul></li>')
    elif apps is not None:
        parts.append('<li class="ok">All apps are up to date.</li>')
    parts += [f'<li class="muted">{esc(p)}</li>' for p in problems]
    return section("Your PC", f"<ul>{''.join(parts)}</ul>" if parts else empty("Update checks only run on Windows."))


def news_html(sections, problems):
    out = []
    for name, items in sections.items():
        if items:
            rows = "".join(f'<li>{link(i.title, i.link)} <span class="muted">· {esc(i.source)}</span>'
                           f'<div class="muted small">{esc(i.summary)}</div></li>' for i in items)
            body = f"<ul>{rows}</ul>"
        else:
            body = empty("No new stories since your last brief.")
        out.append(section(f"{name} news", body))
    if problems:
        out.append(f'<p class="muted small">Couldn\'t load: {esc("; ".join(problems))}</p>')
    return "".join(out)


# ---------------------------------------------------------------- the whole page

CSS = """
:root { color-scheme: light dark; --bg:#f6f7f9; --card:#fff; --text:#1d2330; --muted:#6b7280;
        --accent:#2563eb; --ok:#15803d; --warn:#b45309; }
@media (prefers-color-scheme: dark) { :root { --bg:#111418; --card:#1b1f26; --text:#e7e9ee;
        --muted:#9aa3af; --accent:#7aa7ff; --ok:#4ade80; --warn:#fbbf24; } }
body { margin:0; background:var(--bg); color:var(--text);
       font:16px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width:860px; margin:0 auto; padding:24px 16px 48px; }
h1 { margin:0 0 4px; font-size:28px; } .sub { color:var(--muted); margin:0 0 20px; }
section { background:var(--card); border-radius:12px; padding:16px 20px; margin:0 0 16px;
          box-shadow:0 1px 3px rgba(0,0,0,.08); }
h2 { font-size:18px; margin:0 0 8px; }
ul { margin:0; padding-left:20px; } li { margin:6px 0; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.muted { color:var(--muted); } .small { font-size:14px; }
.time { display:inline-block; min-width:72px; font-weight:600; }
.ok { color:var(--ok); } .warn { color:var(--warn); } .warn li { color:var(--text); }
code { background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }
footer { color:var(--muted); font-size:13px; text-align:center; }
"""


def build_page(d: dict, now: datetime | None = None) -> str:
    """d holds everything gathered by main.py (see main.gather())."""
    now = now or datetime.now()
    hour = now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    body = "".join([
        calendar_html(d["events"], d["google_problem"]),
        email_html(d["emails"], d["google_problem"]),
        updates_html(d["chrome"], d["apps"], d["windows"], d["update_problems"]),
        news_html(d["news"], d["news_problems"]),
    ])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning brief · {esc(now.strftime('%a %b %d'))}</title>
<style>{CSS}</style></head>
<body><main>
<h1>{esc(greeting)}{", " + esc(d["name"]) if d.get("name") else ""}</h1>
<p class="sub">{esc(now.strftime('%A, %B %d, %Y · %I:%M %p').replace(' 0', ' '))}</p>
{body}
<footer>Made by morning-brief · email and calendar were only read · nothing on your PC was changed</footer>
</main></body></html>"""
