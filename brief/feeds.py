"""
Downloads news feeds (RSS or Atom) and turns them into simple Item objects.

A "feed" is a web page in a standard XML format (RSS or Atom) that lists a site's
latest posts or releases. GitHub gives every project one for free at
    https://github.com/OWNER/REPO/releases.atom

This file only uses Python's standard library, so there is nothing to install.
"""
from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# Atom feeds put every tag inside this "namespace". ElementTree needs the full
# name, so <entry> must be written as "{http://www.w3.org/2005/Atom}entry".
ATOM = "{http://www.w3.org/2005/Atom}"

# Articles can have long summaries. We keep only the start, so the page stays
# easy to skim.
MAX_SUMMARY_CHARS = 240


@dataclass
class Item:
    """One update from a feed, reduced to the fields we actually use."""
    id: str        # unique ID from the feed; used to remember what we've already seen
    source: str    # the feed's "name" from settings.json, e.g. "Ars Technica"
    topic: str     # the section it belongs to, e.g. "Tech"
    title: str     # the headline
    link: str      # web address of the full article
    summary: str   # first MAX_SUMMARY_CHARS characters of the notes, as plain text


def clean(text: str | None) -> str:
    """Turn HTML like '<p>New &amp; improved</p>' into plain 'New & improved', then trim."""
    text = re.sub(r"<[^>]+>", " ", text or "")   # remove every <tag>
    text = html.unescape(text)                     # &amp; -> &, &lt; -> <, etc.
    text = re.sub(r"\s+", " ", text).strip()       # collapse runs of spaces/newlines
    if len(text) <= MAX_SUMMARY_CHARS:
        return text
    # Too long: cut at the last space before the limit so no word is chopped in half
    return text[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0] + "…"


def parse_feed(xml_text: str, source: dict) -> list[Item]:
    """Read the XML text of one feed and return its updates as Item objects.

    Handles both common formats:
      Atom (GitHub, Blogger):  <feed><entry><id>, <title>, <link href=...>, <content>
      RSS 2.0 (most blogs):    <rss><channel><item><guid>, <title>, <link>, <description>
    """
    root = ET.fromstring(xml_text)
    items: list[Item] = []

    if root.tag == f"{ATOM}feed":
        for entry in root.findall(f"{ATOM}entry"):
            link_el = entry.find(f"{ATOM}link")
            items.append(Item(
                id=(entry.findtext(f"{ATOM}id") or "").strip(),
                source=source["name"],
                topic=source.get("topic", ""),
                title=clean(entry.findtext(f"{ATOM}title")),
                link=link_el.get("href", "") if link_el is not None else "",
                # Some feeds use <content>, others <summary>; take whichever exists.
                summary=clean(entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary")),
            ))
    else:
        for entry in root.iter("item"):
            link = (entry.findtext("link") or "").strip()
            items.append(Item(
                id=(entry.findtext("guid") or link).strip(),   # no <guid>? use the link as the ID
                source=source["name"],
                topic=source.get("topic", ""),
                title=clean(entry.findtext("title")),
                link=link,
                summary=clean(entry.findtext("description")),
            ))

    # Without an ID we can't tell whether we've seen it before, so drop it.
    return [i for i in items if i.id]


def fetch_source(source: dict, timeout: float = 20) -> list[Item]:
    """Download one feed from the internet and parse it.

    Raises an error if the site is down or blocked; news.py catches it, notes it,
    and carries on with the other feeds.
    """
    request = urllib.request.Request(source["url"], headers={"User-Agent": "morning-brief/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_feed(response.read().decode("utf-8", errors="replace"), source)
