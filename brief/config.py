"""
Where things live.

The CODE (this project folder) can sit anywhere, including OneDrive.
Your DATA (Google keys, sign-in token, saved pages, logs) lives in a separate
folder on this PC only, so private files are never synced to the cloud:

    Windows:  C:\\Users\\<you>\\AppData\\Local\\morning-brief\\
    Other:    ~/.morning-brief/

To use a different data folder, set the environment variable MORNING_BRIEF_DATA.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent   # the morning-brief project folder


def data_dir() -> Path:
    if os.environ.get("MORNING_BRIEF_DATA"):
        return Path(os.environ["MORNING_BRIEF_DATA"])
    if os.environ.get("LOCALAPPDATA"):                  # set on every Windows PC
        return Path(os.environ["LOCALAPPDATA"]) / "morning-brief"
    return Path.home() / ".morning-brief"


def load_settings(root: Path = CODE_ROOT) -> dict:
    return json.loads((root / "settings.json").read_text(encoding="utf-8"))
