"""
Writes a one-line report of every run to logs/runs.jsonl ("JSON Lines": one JSON
object per line, newest at the bottom).

Why: this log is how the future supervisor (admin) agent will check on the brief.
It can read the last line and ask: Did it run today? Did it finish? Were there
errors? Did any section break? Example line:

{"agent": "morning-brief", "run_id": "3bad221eb443", "status": "ok",
 "counts": {"emails": 6, "events": 3, "news": 24, "updates": 7}, "errors": [], ...}

Possible "status" values:
  ok               finished, no problems
  ok_with_errors   finished, but some sections failed (see "errors")
  failed           something broke before the page could be written
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class RunLog:
    def __init__(self, path: Path, agent: str = "morning-brief"):
        self.path = path
        self.record = {
            "agent": agent,
            "run_id": uuid.uuid4().hex[:12],                        # random ID for this run
            "started_at": datetime.now(timezone.utc).isoformat(),  # UTC avoids time-zone confusion
            "status": "running",
            "errors": [],
            "counts": {},
        }
        self._t0 = time.monotonic()   # a clock that only counts up, for measuring duration

    def error(self, where: str, err: Exception | str) -> None:
        """Record a problem without stopping the run."""
        self.record["errors"].append({"where": where, "error": str(err)})

    def count(self, key: str, value: int) -> None:
        self.record["counts"][key] = value

    def finish(self, status: str) -> dict:
        """Stamp the end time and append this run's line to the log file."""
        if status == "ok" and self.record["errors"]:
            status = "ok_with_errors"
        self.record["status"] = status
        self.record["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.record["duration_s"] = round(time.monotonic() - self._t0, 2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:   # "a" = append, never overwrite
            f.write(json.dumps(self.record) + "\n")
        return self.record
