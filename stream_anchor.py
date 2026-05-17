"""Find the latest OBS recording in ~/Movies and parse its filename for stream-start time."""

import os
import re
from datetime import datetime
from pathlib import Path

_FILENAME_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})(?: \(\d+\))?\.mov$"
)


def find_latest_movie(movies_dir="~/Movies"):
    """Return (Path, datetime) for the newest OBS-named .mov file in movies_dir.

    Raises FileNotFoundError if the dir doesn't exist or contains no matching file.
    """
    expanded = Path(os.path.expanduser(str(movies_dir)))
    if not expanded.is_dir():
        raise FileNotFoundError(f"Directory not found: {expanded}")

    matches = []
    for path in expanded.iterdir():
        m = _FILENAME_PATTERN.match(path.name)
        if not m:
            continue
        date_str, hh, mm, ss = m.groups()
        ts = datetime.strptime(f"{date_str} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S")
        matches.append((path, ts))

    if not matches:
        raise FileNotFoundError(f"No OBS recordings (YYYY-MM-DD HH-MM-SS.mov) in {expanded}")

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0]
