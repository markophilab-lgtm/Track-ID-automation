"""SoundCloud API client: OAuth 2.1 + PKCE, token storage, track upload.

Mirrors mixcloud_client.py conventions. Registration of the SoundCloud app
(requires Artist Pro) happens at soundcloud.com/you/apps with redirect URI
exactly http://localhost:8766/callback.
"""

import base64
import hashlib
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
APP_CRED_PATH = SECRETS_DIR / "soundcloud_app.json"
TOKEN_PATH = SECRETS_DIR / "soundcloud.json"

REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8766  # Mixcloud already owns 8765
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

OAUTH_AUTHORIZE = "https://secure.soundcloud.com/authorize"
OAUTH_TOKEN = "https://secure.soundcloud.com/oauth/token"
API_BASE = "https://api.soundcloud.com"

_TIMEOUT = 30
_UPLOAD_TIMEOUT = 1800  # big files: allow 30 minutes
_OAUTH_WAIT_TIMEOUT = 300

MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # SoundCloud hard limit: 4 GB
MAX_UPLOAD_SECONDS = 24 * 3600             # SoundCloud hard limit: 24 hours


class SoundCloudAuthError(Exception):
    """OAuth, token exchange, or token refresh failed."""


class SoundCloudAPIError(Exception):
    """A SoundCloud API call returned a non-success status."""


def _ensure_dir(dir_path):
    Path(dir_path).mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(dir_path, 0o700)


# --- PKCE ---

def make_verifier():
    """64-char url-safe code_verifier (RFC 7636)."""
    return base64.urlsafe_b64encode(os.urandom(48)).decode("ascii").rstrip("=")


def pkce_challenge(verifier):
    """S256 code_challenge for a verifier (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# --- Credential + token storage (path=None -> module constant, patchable in tests) ---

def load_app_credentials(path=None):
    path = Path(path) if path else APP_CRED_PATH
    if not path.exists():
        raise FileNotFoundError(f"SoundCloud app credentials not found at {path}")
    data = json.loads(path.read_text())
    return data["client_id"], data["client_secret"]


def save_app_credentials(client_id, client_secret, path=None):
    path = Path(path) if path else APP_CRED_PATH
    _ensure_dir(path.parent)
    path.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))
    os.chmod(path, 0o600)


def load_token(path=None):
    """Return the saved token dict {access_token, refresh_token}, or None."""
    path = Path(path) if path else TOKEN_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_token(token_dict, path=None):
    path = Path(path) if path else TOKEN_PATH
    _ensure_dir(path.parent)
    path.write_text(json.dumps(token_dict))
    os.chmod(path, 0o600)


# --- OAuth ---

def build_authorize_url(client_id, challenge, redirect_uri=REDIRECT_URI):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return OAUTH_AUTHORIZE + "?" + urllib.parse.urlencode(params)


def _token_request(data):
    resp = requests.post(OAUTH_TOKEN, data=data, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise SoundCloudAuthError(
            f"Token request failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    body = resp.json()
    if "access_token" not in body:
        raise SoundCloudAuthError(f"Token response missing access_token: {body}")
    return {"access_token": body["access_token"],
            "refresh_token": body.get("refresh_token", "")}


def exchange_code_for_token(client_id, client_secret, redirect_uri, code, code_verifier):
    return _token_request({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": code_verifier,
    })


def refresh_access_token(client_id, client_secret, refresh_token):
    return _token_request({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })


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
            self.wfile.write(b"<h1>SoundCloud connected.</h1><p>You can close this tab.</p>")
        else:
            _CallbackHandler.captured_error = qs.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args, **kwargs):  # silence stderr noise
        pass


def run_oauth_flow(client_id, client_secret):
    """Open browser, run local listener on 8766, return token dict. Blocking."""
    _CallbackHandler.captured_code = None
    _CallbackHandler.captured_error = None
    verifier = make_verifier()
    challenge = pkce_challenge(verifier)
    server = http.server.HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = build_authorize_url(client_id, challenge)
        opened = webbrowser.open(url)
        if opened:
            print("\nOpening browser to authorize this app with SoundCloud...")
            print(f"If the browser didn't open, paste this URL manually:\n  {url}\n")
        else:
            print(f"\nCouldn't auto-open browser. Paste this URL into your browser:\n  {url}\n")
        deadline = time.time() + _OAUTH_WAIT_TIMEOUT
        while (_CallbackHandler.captured_code is None
               and _CallbackHandler.captured_error is None
               and time.time() < deadline):
            time.sleep(0.1)
    finally:
        server.shutdown()

    if (_CallbackHandler.captured_code is None
            and _CallbackHandler.captured_error is None):
        raise SoundCloudAuthError(
            f"OAuth timed out after {_OAUTH_WAIT_TIMEOUT}s. Re-run setup and try again."
        )
    if _CallbackHandler.captured_error:
        raise SoundCloudAuthError(f"OAuth error: {_CallbackHandler.captured_error}")
    return exchange_code_for_token(
        client_id, client_secret, REDIRECT_URI, _CallbackHandler.captured_code, verifier
    )


def ensure_token(prompt_for_app_creds_fn=None):
    """Return a valid token dict, running OAuth if needed."""
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
    save_token(token)
    return token
