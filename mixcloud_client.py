"""Mixcloud API client: credential storage, OAuth exchange, cloudcast operations."""

import http.server
import json
import os
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

SECRETS_DIR = Path(os.path.expanduser("~/.tracklist_secrets"))
APP_CRED_PATH = SECRETS_DIR / "mixcloud_app.json"
TOKEN_PATH = SECRETS_DIR / "mixcloud.json"

REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8765
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

OAUTH_AUTHORIZE = "https://www.mixcloud.com/oauth/authorize/"
OAUTH_TOKEN = "https://www.mixcloud.com/oauth/access_token/"

_TIMEOUT = 15


class MixcloudAuthError(Exception):
    """OAuth or token exchange failed."""


class MixcloudAPIError(Exception):
    """A Mixcloud API call returned a non-success status."""


def _ensure_dir(dir_path):
    """Create the directory with mode 700 (and fix mode if it already exists)."""
    Path(dir_path).mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(dir_path, 0o700)


def load_app_credentials(path=APP_CRED_PATH):
    """Return (client_id, client_secret). Raises FileNotFoundError if not set up."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Mixcloud app credentials not found at {path}")
    data = json.loads(Path(path).read_text())
    return data["client_id"], data["client_secret"]


def save_app_credentials(client_id, client_secret, path=APP_CRED_PATH):
    path = Path(path)
    _ensure_dir(path.parent)
    path.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))
    os.chmod(path, 0o600)


def load_token(path=TOKEN_PATH):
    """Return the saved access_token string, or None if not yet saved."""
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text()).get("access_token")


def save_token(path, access_token):
    path = Path(path)
    _ensure_dir(path.parent)
    path.write_text(json.dumps({"access_token": access_token}))
    os.chmod(path, 0o600)


def build_authorize_url(client_id, redirect_uri=REDIRECT_URI):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    return OAUTH_AUTHORIZE + "?" + urllib.parse.urlencode(params)


def exchange_code_for_token(client_id, client_secret, redirect_uri, code):
    """Exchange an OAuth authorization code for an access token. Raises MixcloudAuthError on failure."""
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    resp = requests.post(OAUTH_TOKEN, params=params, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise MixcloudAuthError(
            f"Token exchange failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    body = resp.json()
    if "access_token" not in body:
        raise MixcloudAuthError(f"Token exchange returned no access_token: {body}")
    return body["access_token"]


# --- OAuth browser flow (NOT unit-tested; verified in manual smoke test) ---

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    captured_code = None
    captured_error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            _CallbackHandler.captured_code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Mixcloud connected.</h1><p>You can close this tab.</p>")
        else:
            _CallbackHandler.captured_error = qs.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args, **kwargs):  # silence stderr noise
        pass


def run_oauth_flow(client_id, client_secret):
    """Open browser, run local HTTP listener, return access_token. Blocking."""
    _CallbackHandler.captured_code = None
    _CallbackHandler.captured_error = None
    server = http.server.HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = build_authorize_url(client_id)
        print(f"\nOpening browser to authorize this app with Mixcloud...\n  {url}\n")
        webbrowser.open(url)
        # Wait for the handler to capture either code or error
        while _CallbackHandler.captured_code is None and _CallbackHandler.captured_error is None:
            time.sleep(0.1)
    finally:
        server.shutdown()

    if _CallbackHandler.captured_error:
        raise MixcloudAuthError(f"OAuth error: {_CallbackHandler.captured_error}")
    return exchange_code_for_token(
        client_id, client_secret, REDIRECT_URI, _CallbackHandler.captured_code
    )


def ensure_token(prompt_for_app_creds_fn=None):
    """Return a valid access token, running OAuth if needed.

    prompt_for_app_creds_fn() -> (client_id, client_secret), called interactively
    if no app credentials are saved yet. Pass None to raise instead of prompting.
    """
    try:
        client_id, client_secret = load_app_credentials()
    except FileNotFoundError:
        if prompt_for_app_creds_fn is None:
            raise
        client_id, client_secret = prompt_for_app_creds_fn()
        save_app_credentials(client_id, client_secret)

    token = load_token()
    if token:
        return token

    token = run_oauth_flow(client_id, client_secret)
    save_token(TOKEN_PATH, token)
    return token
