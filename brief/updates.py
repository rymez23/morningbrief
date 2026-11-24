"""
UPDATES SECTION: what on your PC needs updating. Read-only: nothing is installed.

Three checks, each independent:
  chrome_status()      your Chrome version vs. the stable version most users are getting
  winget_upgrades()    apps with updates, via Windows' built-in "winget" tool
  windows_updates()    pending Windows Update items (security, drivers, Defender)

On a non-Windows computer each check returns None, meaning "not available here".
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

IS_WINDOWS = sys.platform == "win32"

# Google's public "version history" service. Chrome updates roll out gradually: a new
# version first goes to ~1% of users, then more over days. This URL lists every version
# currently being served and what fraction of users get it, e.g.
#   {"releases": [{"version": "158.0.8127.89", "fraction": 1.0}, {"version": "159.0.8154.13", "fraction": 0.01}]}
# We only count a version as "the latest" once it reaches at least ROLLOUT_THRESHOLD of
# users, so the brief doesn't nag about an update Chrome won't offer you yet.
CHROME_RELEASES_URL = ("https://versionhistory.googleapis.com/v1/chrome/platforms/win64/"
                       "channels/stable/versions/all/releases?filter=endtime=none")
ROLLOUT_THRESHOLD = 0.5

# Stops Windows from flashing a console window when we run winget / PowerShell
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------- Chrome

def version_tuple(v: str) -> tuple[int, ...]:
    """'158.0.8127.37' -> (158, 0, 8127, 37), so versions compare correctly as numbers.
    (As plain text, '99.0' would wrongly count as newer than '158.0'.)"""
    return tuple(int(part) for part in v.split(".") if part.isdigit())


def installed_chrome_version() -> str | None:
    """Chrome writes its version to the Windows registry under ...\\Google\\Chrome\\BLBeacon."""
    if not IS_WINDOWS:
        return None
    import winreg   # Windows-only standard library module, so it's imported here
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Google\Chrome\BLBeacon") as key:
                return winreg.QueryValueEx(key, "version")[0]
        except OSError:
            continue    # not in this part of the registry; try the next one
    return None


def widely_released(releases: list[dict], threshold: float = ROLLOUT_THRESHOLD) -> str:
    """Highest version that at least `threshold` of users are getting.
    If nothing has reached the threshold yet, use the most widely served one."""
    wide = [r["version"] for r in releases if r.get("fraction", 0) >= threshold]
    if wide:
        return max(wide, key=version_tuple)
    return max(releases, key=lambda r: r.get("fraction", 0))["version"]


def latest_chrome_version(timeout: float = 15) -> str:
    req = urllib.request.Request(CHROME_RELEASES_URL, headers={"User-Agent": "morning-brief/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return widely_released(json.load(resp)["releases"])


def chrome_status(installed: str | None = None, latest: str | None = None) -> dict | None:
    """Returns {"installed", "latest", "up_to_date"}, or None if Chrome isn't found.
    The arguments exist so tests can pass in versions instead of checking the PC."""
    installed = installed or installed_chrome_version()
    if not installed:
        return None
    latest = latest or latest_chrome_version()
    return {"installed": installed, "latest": latest,
            "up_to_date": version_tuple(installed) >= version_tuple(latest)}


# ---------------------------------------------------------------- winget (apps)

def parse_winget_table(text: str) -> list[dict]:
    """Turn winget's printed table into a list of dicts.

    winget prints something like:
        Name     Id        Version  Available  Source
        -----------------------------------------------
        Git      Git.Git   2.56.0   2.56.1     winget
        6 upgrades available.

    Columns are lined up with spaces, but names can contain spaces too, so we
    find where each column STARTS in the header line and slice every row there.
    """
    lines = text.replace("\r", "\n").splitlines()   # winget uses \r for its spinner
    header_i = next((i for i, ln in enumerate(lines)
                     if ln.lstrip().startswith("Name") and " Id " in ln and "Available" in ln), None)
    if header_i is None:
        return []
    header = lines[header_i]
    cols = ["Name", "Id", "Version", "Available", "Source"]
    starts = [header.index(c) for c in cols if c in header]

    rows = []
    for ln in lines[header_i + 2:]:                 # skip the header and the ---- line
        if not ln.strip() or "upgrades available" in ln or "upgrade available" in ln \
                or len(ln) < starts[-1] or "require explicit targeting" in ln:
            break
        cells = [ln[s:e].strip() for s, e in zip(starts, starts[1:] + [None])]
        rows.append(dict(zip(cols, cells)))
    return [{"name": r["Name"], "id": r["Id"], "current": r["Version"], "available": r["Available"]}
            for r in rows if r.get("Id")]


def winget_upgrades(run=subprocess.run) -> list[dict] | None:
    if not IS_WINDOWS:
        return None
    # --source winget: only the community catalog (the Microsoft Store source
    #   would ask you to accept its terms first)
    # --disable-interactivity: never stop and wait for keyboard input
    out = run(["winget", "upgrade", "--source", "winget", "--disable-interactivity"],
              capture_output=True, text=True, encoding="utf-8", errors="replace",
              timeout=120, creationflags=NO_WINDOW)
    return parse_winget_table(out.stdout)


# ---------------------------------------------------------------- Windows Update

# PowerShell asks the Windows Update service (the same one Settings uses) for
# updates that are available but not installed, and prints their titles as JSON.
WU_SCRIPT = (
    "$s = New-Object -ComObject Microsoft.Update.Session;"
    "$r = $s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0');"
    "@($r.Updates | ForEach-Object { $_.Title }) | ConvertTo-Json -Compress"
)


def windows_updates(run=subprocess.run) -> list[str] | None:
    if not IS_WINDOWS:
        return None
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", WU_SCRIPT],
              capture_output=True, text=True, encoding="utf-8", errors="replace",
              timeout=300, creationflags=NO_WINDOW)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300] or "Windows Update check failed")
    text = out.stdout.strip()
    if not text:
        return []
    data = json.loads(text)
    return [data] if isinstance(data, str) else data   # one result comes back as a plain string
