#!/usr/bin/env python3
"""Extract audio from a stream recording and upload it to SoundCloud.

Usage:
  python3 soundcloud_publish.py --setup            # first-run: creds + browser OAuth
  python3 soundcloud_publish.py --movie X.mov --title "T" --description-file D.txt [--dry-run] [--keep-audio]

Exit codes: 0 ok, 2 input problem, 3 ffmpeg missing/failed, 4 auth failure, 5 upload failure.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import soundcloud_client
from clipboard_and_notify import notify


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def extract_audio(movie_path, out_path):
    """MOV -> 320 kbps MP3. Raises subprocess.CalledProcessError on failure."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(movie_path), "-vn",
         "-codec:a", "libmp3lame", "-b:a", "320k", str(out_path)],
        check=True, capture_output=True,
    )
    return Path(out_path)


def probe_duration_seconds(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def _prompt_app_creds():
    print("\nFirst-time SoundCloud setup:")
    print("  1. Go to https://soundcloud.com/you/apps (requires SoundCloud Artist Pro)")
    print("  2. Register an app with redirect URI exactly: http://localhost:8766/callback")
    print("  3. Copy the Client ID and Client Secret it gives you.")
    cid = input("\nClient ID: ").strip()
    secret = input("Client Secret: ").strip()
    return cid, secret


def _run_setup():
    try:
        client_id, client_secret = soundcloud_client.load_app_credentials()
        print("App credentials already saved; re-running browser authorization.")
    except FileNotFoundError:
        client_id, client_secret = _prompt_app_creds()
        soundcloud_client.save_app_credentials(client_id, client_secret)
    try:
        token = soundcloud_client.run_oauth_flow(client_id, client_secret)
    except soundcloud_client.SoundCloudAuthError as e:
        print(f"Setup failed: {e}", file=sys.stderr)
        return 4
    soundcloud_client.save_token(token)
    print("SoundCloud connected. You're ready to upload.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Upload a set's audio to SoundCloud.")
    p.add_argument("--setup", action="store_true", help="First-run: app credentials + browser OAuth")
    p.add_argument("--movie", help="Path to the .mov recording")
    p.add_argument("--title", help="Track title")
    p.add_argument("--description-file", help="File containing the track description")
    p.add_argument("--tags", default='"DJ mix" livestream', help="SoundCloud tag_list")
    p.add_argument("--dry-run", action="store_true", help="Preview only; upload nothing")
    p.add_argument("--keep-audio", action="store_true",
                   help="Keep the extracted MP3 next to the movie instead of deleting it")
    args = p.parse_args(argv)

    if args.setup:
        return _run_setup()

    if not (args.movie and args.title and args.description_file):
        p.error("--movie, --title and --description-file are required (or use --setup)")

    movie = Path(os.path.expanduser(args.movie))
    if not movie.is_file():
        print(f"Error: movie not found: {movie}", file=sys.stderr)
        return 2
    desc_path = Path(os.path.expanduser(args.description_file))
    if not desc_path.is_file():
        print(f"Error: description file not found: {desc_path}", file=sys.stderr)
        return 2
    description = desc_path.read_text()

    if not ffmpeg_available():
        print("Error: ffmpeg/ffprobe not installed. Install with:\n  brew install ffmpeg",
              file=sys.stderr)
        return 3

    try:
        duration = probe_duration_seconds(movie)
    except subprocess.CalledProcessError as e:
        print(f"Error: ffprobe failed on {movie}: {e.stderr}", file=sys.stderr)
        return 3
    if duration > soundcloud_client.MAX_UPLOAD_SECONDS:
        print(f"Error: recording is {duration / 3600:.1f} h — over SoundCloud's 24 h limit",
              file=sys.stderr)
        return 2

    est_mb = duration * 320_000 / 8 / 1e6  # 320 kbps
    if args.dry_run:
        print("--- DRY RUN: what would be uploaded to SoundCloud ---")
        print(f"Title:       {args.title}")
        print(f"Duration:    {duration / 60:.1f} min")
        print(f"Est. size:   {est_mb:.0f} MB (320 kbps MP3)")
        print(f"Tags:        {args.tags}")
        print("Description:")
        print(description)
        print("--- end dry run (nothing uploaded) ---")
        return 0

    if args.keep_audio:
        mp3_path = movie.with_suffix(".mp3")
        tmp_dir = None
    else:
        tmp_dir = tempfile.TemporaryDirectory()
        mp3_path = Path(tmp_dir.name) / (movie.stem + ".mp3")

    try:
        print(f"Extracting audio ({duration / 60:.1f} min, ~{est_mb:.0f} MB)...", file=sys.stderr)
        try:
            audio = extract_audio(movie, mp3_path)
        except subprocess.CalledProcessError as e:
            print(f"Error: ffmpeg failed: {e.stderr[-500:] if e.stderr else e}", file=sys.stderr)
            return 3

        print("Uploading to SoundCloud (this can take a while)...", file=sys.stderr)
        try:
            url = soundcloud_client.upload_track(audio, args.title, description, tags=args.tags)
        except soundcloud_client.SoundCloudAuthError as e:
            print(f"Auth error: {e}", file=sys.stderr)
            return 4
        except soundcloud_client.SoundCloudAPIError as e:
            print(f"Upload error: {e}", file=sys.stderr)
            return 5

        print(f"Uploaded: {url}")
        try:
            notify("SoundCloud upload done", url or args.title)
        except Exception:
            pass
        return 0
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()


if __name__ == "__main__":
    sys.exit(main())
