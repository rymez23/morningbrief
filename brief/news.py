"""
NEWS SECTION: the newest headlines you haven't seen yet, grouped by section.

For each section in settings.json (Tech, Politics, Science), it:
  1. downloads every feed in that section
  2. drops stories already shown on an earlier morning (seen.py)
  3. takes stories from the feeds in turn (1st from feed A, 1st from feed B, ...)
     so one busy site can't fill the whole section
  4. stops at news_per_section stories
"""
from __future__ import annotations

from itertools import zip_longest

from .feeds import Item, fetch_source
from .seen import SeenStore


def interleave(lists: list[list[Item]]) -> list[Item]:
    """[[a1, a2], [b1]] -> [a1, b1, a2]  (take one from each list in turn)."""
    return [item for group in zip_longest(*lists) for item in group if item is not None]


def gather_news(settings: dict, seen: SeenStore, fetcher=fetch_source) -> tuple[dict[str, list[Item]], list[str]]:
    """Returns ({section name: [stories]}, [error messages]).

    The shown stories are added to `seen`; the caller saves it at the end.
    """
    per_section = settings.get("news_per_section", 6)
    sections: dict[str, list[Item]] = {}
    errors: list[str] = []

    for section, feeds in settings.get("news", {}).items():
        per_feed = []
        for feed in feeds:
            try:
                items = fetcher({"name": feed["name"], "url": feed["url"], "topic": section})
                per_feed.append([i for i in items if seen.is_new(i.id)])
            except Exception as e:      # one broken site shouldn't hide the others
                errors.append(f"{feed['name']}: {e}")
        chosen = interleave(per_feed)[:per_section]
        seen.add(i.id for i in chosen)
        sections[section] = chosen

    return sections, errors
