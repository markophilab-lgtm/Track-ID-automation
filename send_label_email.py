#!/usr/bin/env python3
"""Send ONE label-outreach email via Gmail SMTP (app-password auth).

Used only when ~/.tracklist_secrets/outreach_mode.txt says "send".
Exit codes: 0 sent, 2 config/input problem, 4 auth rejected, 5 send failed.
"""

import argparse
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

CONFIG_PATH = Path(os.path.expanduser("~/.tracklist_secrets/gmail_smtp.json"))

SETUP_HELP = """\
Gmail SMTP is not configured yet. One-time setup:
  1. Go to myaccount.google.com -> Security -> 2-Step Verification (must be ON)
  2. Search for "App passwords" -> create one named "label outreach"
  3. Run: python3 send_label_email.py --save-config   and paste it when asked
You can revoke the app password any time from the same Google page."""


def load_config(path=None):
    path = Path(path) if path else CONFIG_PATH
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not data.get("address") or not data.get("app_password"):
        return None
    return data


def save_config(address, app_password, path=None):
    path = Path(path) if path else CONFIG_PATH
    path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(path.parent, 0o700)
    path.write_text(json.dumps({"address": address, "app_password": app_password}))
    os.chmod(path, 0o600)


def build_message(from_addr, to_addr, subject, body):
    """One recipient only — a comma/semicolon in --to is always a mistake here."""
    if "," in to_addr or ";" in to_addr:
        raise ValueError(f"exactly one recipient per send, got: {to_addr}")
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send(msg, config):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(config["address"], config["app_password"])
        s.send_message(msg)


def main(argv=None):
    p = argparse.ArgumentParser(description="Send one outreach email via Gmail SMTP.")
    p.add_argument("--save-config", action="store_true", help="Store Gmail address + app password")
    p.add_argument("--to", help="Recipient (exactly one)")
    p.add_argument("--subject")
    p.add_argument("--body-file", help="File containing the plain-text body")
    args = p.parse_args(argv)

    if args.save_config:
        address = input("Gmail address: ").strip()
        app_password = input("App password: ").strip()
        save_config(address, app_password)
        print("Saved.")
        return 0

    config = load_config()
    if config is None:
        print(SETUP_HELP, file=sys.stderr)
        return 2
    if not (args.to and args.subject and args.body_file):
        p.error("--to, --subject and --body-file are required (or use --save-config)")

    body = Path(os.path.expanduser(args.body_file)).read_text()
    try:
        msg = build_message(config["address"], args.to, args.subject, body)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    try:
        send(msg, config)
    except smtplib.SMTPAuthenticationError:
        print("ERROR: Gmail rejected the app password. Re-run --save-config, and check "
              "that 2-Step Verification is still on.", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"ERROR: send failed: {e}", file=sys.stderr)
        return 5
    print(f"Sent to {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
