"""
Remembers which news headlines were already shown, so each morning only shows
stories you haven't seen yet.

The memory is a plain JSON list of feed IDs saved in state/seen.json.
Delete that file and the brief forgets everything (the next run shows the latest
stories again).
"""
from __future__ import annotations

import json
from pathlib import Path


class SeenStore:
    def __init__(self, path: Path):
        self.path = path
        self.ids: set[str] = set()   # a set makes "have I seen this?" checks instant
        if path.exists():
            self.ids = set(json.loads(path.read_text(encoding="utf-8")))

    def is_new(self, item_id: str) -> bool:
        return item_id not in self.ids

    def add(self, item_ids) -> None:
        self.ids.update(item_ids)

    def save(self) -> None:
        """Write to a temporary file first, then swap it into place.

        If the computer crashes halfway through writing, the old seen.json is
        still intact instead of being left half-written and unreadable.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(self.ids), indent=0), encoding="utf-8")
        tmp.replace(self.path)
