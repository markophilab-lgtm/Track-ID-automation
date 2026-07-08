#!/usr/bin/env python3
"""Upload a file to Gofile and print the download link.

Usage:
  python3 gofile_upload.py --file X.mov [--dry-run]

Reads the API token from ~/.tracklist_secrets/gofile.json:
  {"account_id": "...", "api_token": "..."}

Exit codes: 0 ok, 2 input problem, 4 auth failure, 5 upload failure.

Free-tier note: Gofile guarantees files for ~10 days without downloads, so tell
the recipient to grab the file within a week.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from clipboard_and_notify import notify

SECRETS_DIR = Path(os.path.expanduser("~/.tracklist_secrets"))
TOKEN_PATH = SECRETS_DIR / "gofile.json"
SERVERS_URL = "https://api.gofile.io/servers"


class GofileAuthError(Exception):
    pass


class GofileUploadError(Exception):
    pass


def load_token():
    if not TOKEN_PATH.is_file():
        raise GofileAuthError(
            f"No Gofile credentials at {TOKEN_PATH}. Create a free account at "
            "gofile.io, copy the API token from your profile page, and save it as "
            '{"account_id": "...", "api_token": "..."}'
        )
    data = json.loads(TOKEN_PATH.read_text())
    token = data.get("api_token", "").strip()
    if not token:
        raise GofileAuthError(f"api_token missing or empty in {TOKEN_PATH}")
    return token


def pick_server():
    """Ask Gofile which upload server to use; prefer an EU one (we're in NL)."""
    with urllib.request.urlopen(SERVERS_URL, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    servers = payload.get("data", {}).get("servers", [])
    if not servers:
        raise GofileUploadError("Gofile returned no upload servers")
    for s in servers:
        if s.get("zone") == "eu":
            return s["name"]
    return servers[0]["name"]


def upload(file_path, token, server):
    """Stream the file to Gofile via curl (handles multi-GB uploads reliably)."""
    result = subprocess.run(
        ["curl", "-sS", "-H", f"Authorization: Bearer {token}",
         "-F", f"file=@{file_path}",
         f"https://{server}.gofile.io/contents/uploadfile"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GofileUploadError(f"curl failed: {result.stderr.strip()[-300:]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise GofileUploadError(f"unexpected Gofile response: {result.stdout[:300]}")
    status = payload.get("status", "")
    if status != "ok":
        if "auth" in status or "token" in status:
            raise GofileAuthError(f"Gofile rejected the token: {status}")
        raise GofileUploadError(f"Gofile error: {status}")
    link = payload.get("data", {}).get("downloadPage")
    if not link:
        raise GofileUploadError("Gofile response had no download link")
    return link


def main(argv=None):
    p = argparse.ArgumentParser(description="Upload a file to Gofile, print the link.")
    p.add_argument("--file", required=True, help="Path to the file to upload")
    p.add_argument("--dry-run", action="store_true", help="Preview only; upload nothing")
    args = p.parse_args(argv)

    path = Path(os.path.expanduser(args.file))
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 2
    size_gb = path.stat().st_size / 1e9

    if args.dry_run:
        print("--- DRY RUN: what would be uploaded to Gofile ---")
        print(f"File:  {path.name}")
        print(f"Size:  {size_gb:.2f} GB")
        print("--- end dry run (nothing uploaded) ---")
        return 0

    try:
        token = load_token()
    except GofileAuthError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        return 4

    try:
        server = pick_server()
        print(f"Uploading {path.name} ({size_gb:.2f} GB) to Gofile "
              f"[{server}] — this can take a while...", file=sys.stderr)
        link = upload(path, token, server)
    except GofileAuthError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        return 4
    except (GofileUploadError, OSError) as e:
        print(f"Upload error: {e}", file=sys.stderr)
        return 5

    print(link)
    try:
        notify("Gofile upload done", link)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
