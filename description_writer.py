"""Write per-run description files + metadata consumed by the deploy pipeline."""

import json
import os
from pathlib import Path


def write_outputs(out_dir, youtube_description, soundcloud_description, meta):
    """Write youtube_description.txt, soundcloud_description.txt, run_meta.json.

    out_dir is created if missing (parents too). meta keys: stream_start (ISO
    string), movie_path (str), title (str), chapter_count (int).
    Returns out_dir as a Path.
    """
    out_dir = Path(os.path.expanduser(str(out_dir)))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "youtube_description.txt").write_text(youtube_description)
    (out_dir / "soundcloud_description.txt").write_text(soundcloud_description)
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    return out_dir


def default_title(stream_date):
    """stream_date is a datetime.date."""
    return f"waterhousestudios live stream {stream_date.isoformat()}"
