# Deploy Content v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One "deploy content" command that builds the tracklist, uploads the set's audio to SoundCloud via the official API, publishes the video on YouTube via browser automation, and runs label allowlist-outreach — Mixcloud dropped.

**Architecture:** New `soundcloud_client.py` (OAuth 2.1 + PKCE, mirrors `mixcloud_client.py` conventions) and `soundcloud_publish.py` CLI (ffmpeg audio extract + upload); `post_tracklist.py` gains `--write-descriptions DIR` so downstream stages read description files instead of the clipboard; `send_label_email.py` adds an SMTP send path used only in "send" mode; the `label-emailer` agent and `/deploy-content` command are updated to orchestrate all four stages.

**Tech Stack:** Python 3.9 (stdlib + `requests` only — no new pip deps), ffmpeg via Homebrew, existing homegrown test harness (`python3 tests/run_all.py`, plain `assert` + `unittest.mock`, no pytest).

**Spec:** `docs/superpowers/specs/2026-07-03-deploy-content-v2-design.md`

## Global Constraints

- Project root: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT` — **the path contains spaces; always quote it in shell commands.**
- All work happens on `main` in that repo; commit after every task.
- Secrets live in `~/.tracklist_secrets/` — dir mode 700, files mode 600, never committed (`.gitignore` already excludes; verify in Task 10).
- Tests: plain functions named `test_*` using bare `assert`, stubs via `unittest.mock`; **no network, no real secrets dir, no pytest**. Run everything with `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`.
- SoundCloud endpoints (verified 2026-07-03): authorize `https://secure.soundcloud.com/authorize`, token `https://secure.soundcloud.com/oauth/token`, API base `https://api.soundcloud.com`, auth header `Authorization: OAuth <access_token>`, upload `POST /tracks` multipart with `track[title]`, `track[description]`, `track[sharing]`, `track[tag_list]`, `track[asset_data]`.
- OAuth redirect: `http://localhost:8766/callback` (**8766** — Mixcloud already owns 8765).
- Upload limits enforced client-side: 4 GB, 24 hours.
- Copy strings verbatim: promo note `Promotional use only — not monetized.` (em-dash); default title `waterhousestudios live stream YYYY-MM-DD`.
- End every commit message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Promo note in the YouTube description formatter

**Files:**
- Modify: `youtube_formatter.py:22-29`
- Test: `tests/test_youtube_formatter.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `format_youtube(chapters, stream_date) -> str` now ends with the line `Promotional use only — not monetized.`; module constant `PROMO_NOTE` holds that exact string.

- [ ] **Step 1: Update the exact-match test and add a promo-note test**

In `tests/test_youtube_formatter.py`, change the `expected` block of `test_full_description` (the final line changes) and append a new test at the bottom of the file:

```python
# inside test_full_description, replace the expected assignment with:
    expected = (
        "Tracklist:\n"
        "\n"
        "0:00 Intro\n"
        "5:23 Anthony Naples — Crystals | https://discogs.com/release/12345 | https://song.link/i/abc\n"
        "12:47 Joy Orbison — Hyph Mngo | https://discogs.com/release/67890 | https://song.link/i/def\n"
        "\n"
        "Recorded live 2026-05-17.\n"
        "Promotional use only — not monetized."
    )
```

```python
# appended at the end of the file:
def test_promo_note_is_last_line():
    chapters = [_chap(0, "0:00", "Intro", "Intro")]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert out.splitlines()[-1] == "Promotional use only — not monetized."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: `test_full_description` and `test_promo_note_is_last_line` FAIL; everything else passes.

- [ ] **Step 3: Implement**

In `youtube_formatter.py`, add a module constant after the docstring and append the line in `format_youtube`:

```python
PROMO_NOTE = "Promotional use only — not monetized."
```

```python
def format_youtube(chapters, stream_date):
    """Return the YouTube description string. stream_date is a datetime.date."""
    lines = ["Tracklist:", ""]
    for ch in chapters:
        lines.append(_chapter_line(ch))
    lines.append("")
    lines.append(f"Recorded live {stream_date.isoformat()}.")
    lines.append(PROMO_NOTE)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all tests PASS (was 62+; now one more).

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add youtube_formatter.py tests/test_youtube_formatter.py && git commit -m "feat: append promotional-use note to YouTube description

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `description_writer.py` — per-run output files

**Files:**
- Create: `description_writer.py`
- Test: `tests/test_description_writer.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `write_outputs(out_dir, youtube_description: str, soundcloud_description: str, meta: dict) -> Path` (creates `out_dir`, writes `youtube_description.txt`, `soundcloud_description.txt`, `run_meta.json`); `default_title(stream_date: datetime.date) -> str` returning `waterhousestudios live stream YYYY-MM-DD`. Task 3 calls both; Stage 2/3 of the command read the files.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_description_writer.py`:

```python
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from description_writer import write_outputs, default_title


def test_writes_all_three_files():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "deploy_output"
        meta = {"stream_start": "2026-05-17T20:00:00", "movie_path": "/tmp/x.mov",
                "title": "t", "chapter_count": 3}
        returned = write_outputs(out, "YT DESC", "SC DESC", meta)
        assert returned == out
        assert (out / "youtube_description.txt").read_text() == "YT DESC"
        assert (out / "soundcloud_description.txt").read_text() == "SC DESC"
        assert json.loads((out / "run_meta.json").read_text()) == meta


def test_creates_missing_directory_and_overwrites():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "a" / "b"
        meta = {"stream_start": "s", "movie_path": "m", "title": "t", "chapter_count": 1}
        write_outputs(out, "one", "one", meta)
        write_outputs(out, "two", "two", meta)
        assert (out / "youtube_description.txt").read_text() == "two"


def test_default_title():
    assert default_title(date(2026, 5, 17)) == "waterhousestudios live stream 2026-05-17"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: the three new tests ERROR with `ModuleNotFoundError: No module named 'description_writer'`.

- [ ] **Step 3: Implement**

Create `description_writer.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add description_writer.py tests/test_description_writer.py && git commit -m "feat: description_writer writes per-run description files + meta

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire `--write-descriptions` into `post_tracklist.py`

**Files:**
- Modify: `post_tracklist.py` (imports ~line 30, argparse ~line 110-118, after the descriptions are built ~line 168-175)
- Test: `tests/test_post_tracklist_writes.py` (new file — keeps the existing integration test untouched)

**Interfaces:**
- Consumes: `write_outputs`, `default_title` from Task 2.
- Produces: CLI flag `--write-descriptions DIR`. On a real (non-dry) run it writes the three files; on `--dry-run` or without the flag it writes nothing. `run_meta.json` fields: `stream_start` (ISO), `movie_path` (str), `title` (default title), `chapter_count` (int).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_post_tracklist_writes.py`:

```python
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import post_tracklist

_LOG = (
    "─── Session started 2026-05-17 20:00:00 ───\n"
    "20:00:05  [Player 1]  Anthony Naples — Crystals\n"
    "20:05:00  [Player 2]  Joy Orbison — Hyph Mngo\n"
)


def _run(argv):
    with mock.patch.object(post_tracklist, "_enrich_chapters"), \
         mock.patch.object(post_tracklist, "notify"):
        return post_tracklist.main(argv)


def test_write_descriptions_writes_files_and_meta():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        out = Path(td) / "out"
        rc = _run(["--movie", str(movie), "--log", str(log),
                   "--skip-mixcloud", "--skip-youtube",
                   "--write-descriptions", str(out)])
        assert rc == 0
        yt = (out / "youtube_description.txt").read_text()
        assert "Tracklist:" in yt
        assert (out / "soundcloud_description.txt").read_text() == yt
        meta = json.loads((out / "run_meta.json").read_text())
        assert meta["title"] == "waterhousestudios live stream 2026-05-17"
        assert meta["movie_path"] == str(movie)
        assert meta["stream_start"] == "2026-05-17T20:00:00"
        assert meta["chapter_count"] >= 1


def test_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        out = Path(td) / "out"
        rc = _run(["--movie", str(movie), "--log", str(log), "--dry-run",
                   "--skip-mixcloud", "--skip-youtube",
                   "--write-descriptions", str(out)])
        assert rc == 0
        assert not out.exists()


def test_flag_absent_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        rc = _run(["--movie", str(movie), "--log", str(log),
                   "--skip-mixcloud", "--skip-youtube"])
        assert rc == 0
        assert not (Path(td) / "out").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: `test_write_descriptions_writes_files_and_meta` FAILs (unrecognized argument `--write-descriptions` causes SystemExit → ERROR); the two "writes nothing" tests also ERROR the same way.

- [ ] **Step 3: Implement**

In `post_tracklist.py`, add to the imports block (after the `clipboard_and_notify` import):

```python
from description_writer import write_outputs, default_title
```

Add to argparse (after the `--skip-youtube` line):

```python
    parser.add_argument("--write-descriptions", metavar="DIR", default=None,
                        help="Write description files + run_meta.json to DIR (skipped on --dry-run)")
```

Insert after the descriptions are built and after the `--dry-run` early return (i.e. right before the `# 7. Mixcloud` block):

```python
    # 6.5 Write description files for downstream stages (SoundCloud upload + YouTube browser publish)
    if args.write_descriptions:
        meta = {
            "stream_start": stream_start.isoformat(),
            "movie_path": str(movie_path),
            "title": default_title(stream_start.date()),
            "chapter_count": len(chapters),
        }
        out_dir = write_outputs(args.write_descriptions, yt_description, yt_description, meta)
        print(f"Descriptions written to {out_dir}", file=sys.stderr)
```

(SoundCloud gets the same text as YouTube — SoundCloud renders the timestamps as seek links.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add post_tracklist.py tests/test_post_tracklist_writes.py && git commit -m "feat: post_tracklist --write-descriptions emits files for downstream stages

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `soundcloud_client.py` — PKCE, credentials, tokens, OAuth flow

**Files:**
- Create: `soundcloud_client.py`
- Test: `tests/test_soundcloud_client.py`

**Interfaces:**
- Consumes: nothing project-internal.
- Produces (used by Tasks 5–6):
  - `SoundCloudAuthError(Exception)`, `SoundCloudAPIError(Exception)`
  - `make_verifier() -> str`, `pkce_challenge(verifier: str) -> str`
  - `save_app_credentials(client_id, client_secret, path=None)`, `load_app_credentials(path=None) -> (str, str)`
  - `save_token(token_dict: dict, path=None)`, `load_token(path=None) -> dict | None` (dict has `access_token`, `refresh_token`)
  - `build_authorize_url(client_id, challenge, redirect_uri=REDIRECT_URI) -> str`
  - `exchange_code_for_token(client_id, client_secret, redirect_uri, code, code_verifier) -> dict`
  - `refresh_access_token(client_id, client_secret, refresh_token) -> dict`
  - `run_oauth_flow(client_id, client_secret) -> dict` (browser + localhost:8766 listener, NOT unit-tested)
  - `ensure_token(prompt_for_app_creds_fn=None) -> dict`
  - Constants: `REDIRECT_URI`, `OAUTH_AUTHORIZE`, `OAUTH_TOKEN`, `API_BASE`, `MAX_UPLOAD_BYTES`, `TOKEN_PATH`, `APP_CRED_PATH`
  - **Path convention:** every path parameter defaults to `None` and resolves to the module-level constant *at call time*, so tests can `mock.patch.object(soundcloud_client, "TOKEN_PATH", tmp)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_soundcloud_client.py`:

```python
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import soundcloud_client as sc


def test_pkce_challenge_rfc7636_vector():
    # Known vector from RFC 7636 appendix B
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert sc.pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_make_verifier_is_urlsafe_and_long_enough():
    v = sc.make_verifier()
    assert 43 <= len(v) <= 128
    assert "=" not in v and "+" not in v and "/" not in v


def test_token_save_load_roundtrip_and_modes():
    import os
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "secrets" / "soundcloud.json"
        tok = {"access_token": "a", "refresh_token": "r"}
        sc.save_token(tok, path=p)
        assert sc.load_token(path=p) == tok
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"
        assert oct(os.stat(p.parent).st_mode & 0o777) == "0o700"


def test_load_token_missing_returns_none():
    with tempfile.TemporaryDirectory() as td:
        assert sc.load_token(path=Path(td) / "nope.json") is None


def test_build_authorize_url_contains_pkce_params():
    url = sc.build_authorize_url("CID", "CHAL")
    assert url.startswith("https://secure.soundcloud.com/authorize?")
    assert "client_id=CID" in url
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "localhost%3A8766" in url


def _resp(status, body):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = body
    r.text = json.dumps(body)
    return r


def test_exchange_code_sends_verifier_and_returns_tokens():
    with mock.patch.object(sc.requests, "post",
                           return_value=_resp(200, {"access_token": "A", "refresh_token": "R"})) as m:
        out = sc.exchange_code_for_token("cid", "sec", sc.REDIRECT_URI, "thecode", "theverifier")
    assert out["access_token"] == "A" and out["refresh_token"] == "R"
    sent = m.call_args.kwargs["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code_verifier"] == "theverifier"
    assert sent["code"] == "thecode"


def test_exchange_code_failure_raises_auth_error():
    with mock.patch.object(sc.requests, "post", return_value=_resp(401, {"error": "bad"})):
        try:
            sc.exchange_code_for_token("cid", "sec", sc.REDIRECT_URI, "c", "v")
            assert False, "should have raised"
        except sc.SoundCloudAuthError:
            pass


def test_refresh_returns_new_token_dict():
    with mock.patch.object(sc.requests, "post",
                           return_value=_resp(200, {"access_token": "A2", "refresh_token": "R2"})) as m:
        out = sc.refresh_access_token("cid", "sec", "oldR")
    assert out == {"access_token": "A2", "refresh_token": "R2"}
    assert m.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert m.call_args.kwargs["data"]["refresh_token"] == "oldR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: new tests ERROR with `ModuleNotFoundError: No module named 'soundcloud_client'`.

- [ ] **Step 3: Implement**

Create `soundcloud_client.py`:

```python
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

    def log_message(self, *args, **kwargs):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add soundcloud_client.py tests/test_soundcloud_client.py && git commit -m "feat: soundcloud_client OAuth 2.1 PKCE auth + token storage

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `soundcloud_client.upload_track` with 401-refresh and retry

**Files:**
- Modify: `soundcloud_client.py` (append after `ensure_token`)
- Test: `tests/test_soundcloud_client.py` (append)

**Interfaces:**
- Consumes: Task 4's storage + refresh functions.
- Produces: `upload_track(audio_path, title, description, tags="") -> str` (returns the new track's `permalink_url`). Behavior: size check before any network; load token (raise `SoundCloudAuthError` with the exact message `No SoundCloud token saved. Run: python3 soundcloud_publish.py --setup` if none); on 401 → refresh once, save, retry; on other non-2xx → sleep 5 s, retry once, then raise `SoundCloudAPIError` with a body summary.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_soundcloud_client.py`:

```python
def _upload_env(td, post_responses, refresh_result=None):
    """Patch token/creds paths into td and requests.post with a response sequence."""
    tok_path = Path(td) / "soundcloud.json"
    cred_path = Path(td) / "soundcloud_app.json"
    sc.save_token({"access_token": "OLD", "refresh_token": "R"}, path=tok_path)
    sc.save_app_credentials("cid", "sec", path=cred_path)
    patches = [
        mock.patch.object(sc, "TOKEN_PATH", tok_path),
        mock.patch.object(sc, "APP_CRED_PATH", cred_path),
        mock.patch.object(sc.time, "sleep"),
        mock.patch.object(sc.requests, "post", side_effect=post_responses),
    ]
    if refresh_result is not None:
        patches.append(mock.patch.object(sc, "refresh_access_token",
                                         return_value=refresh_result))
    return patches, tok_path


def test_upload_success_returns_permalink():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x" * 10)
        patches, _ = _upload_env(td, [_resp(201, {"permalink_url": "https://soundcloud.com/u/set"})])
        with patches[0], patches[1], patches[2], patches[3] as m:
            url = sc.upload_track(audio, "My Set", "desc", tags="dj mix")
        assert url == "https://soundcloud.com/u/set"
        assert m.call_args.kwargs["data"]["track[title]"] == "My Set"
        assert m.call_args.kwargs["data"]["track[sharing]"] == "public"
        assert m.call_args.kwargs["data"]["track[tag_list]"] == "dj mix"
        assert "track[asset_data]" in m.call_args.kwargs["files"]
        assert m.call_args.kwargs["headers"]["Authorization"] == "OAuth OLD"


def test_upload_refreshes_on_401_and_saves_new_token():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        patches, tok_path = _upload_env(
            td,
            [_resp(401, {}), _resp(201, {"permalink_url": "https://sc/u/s"})],
            refresh_result={"access_token": "NEW", "refresh_token": "R2"},
        )
        with patches[0], patches[1], patches[2], patches[3] as m, patches[4]:
            url = sc.upload_track(audio, "t", "d")
        assert url == "https://sc/u/s"
        assert m.call_args.kwargs["headers"]["Authorization"] == "OAuth NEW"
        assert sc.load_token(path=tok_path)["access_token"] == "NEW"


def test_upload_rejects_oversize_file_before_network():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x" * 100)
        with mock.patch.object(sc, "MAX_UPLOAD_BYTES", 50), \
             mock.patch.object(sc.requests, "post") as m:
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAPIError as e:
                assert "4 GB" in str(e) or "limit" in str(e)
        assert m.call_count == 0


def test_upload_no_token_raises_with_setup_hint():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        with mock.patch.object(sc, "TOKEN_PATH", Path(td) / "missing.json"):
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAuthError as e:
                assert "--setup" in str(e)


def test_upload_server_error_retries_once_then_raises():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        patches, _ = _upload_env(td, [_resp(500, {"error": "boom"}),
                                      _resp(500, {"error": "boom"})])
        with patches[0], patches[1], patches[2], patches[3] as m:
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAPIError as e:
                assert "500" in str(e)
        assert m.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: the five new tests ERROR with `AttributeError: ... has no attribute 'upload_track'`.

- [ ] **Step 3: Implement**

Append to `soundcloud_client.py`:

```python
# --- Track upload ---

def _post_tracks(access_token, audio_path, title, description, tags):
    data = {
        "track[title]": title,
        "track[description]": description,
        "track[sharing]": "public",
    }
    if tags:
        data["track[tag_list]"] = tags
    with open(audio_path, "rb") as f:
        files = {"track[asset_data]": (Path(audio_path).name, f, "audio/mpeg")}
        return requests.post(
            f"{API_BASE}/tracks",
            headers={"Authorization": f"OAuth {access_token}"},
            data=data, files=files, timeout=_UPLOAD_TIMEOUT,
        )


def _refresh_and_save(token):
    client_id, client_secret = load_app_credentials()
    new_token = refresh_access_token(client_id, client_secret, token["refresh_token"])
    save_token(new_token)
    return new_token


def upload_track(audio_path, title, description, tags=""):
    """Upload an audio file as a public track. Returns its permalink URL.

    Raises SoundCloudAuthError (no/expired token) or SoundCloudAPIError.
    """
    audio_path = Path(audio_path)
    size = audio_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise SoundCloudAPIError(
            f"File is {size / 1e9:.1f} GB — over SoundCloud's 4 GB upload limit"
        )

    token = load_token()
    if not token:
        raise SoundCloudAuthError(
            "No SoundCloud token saved. Run: python3 soundcloud_publish.py --setup"
        )

    resp = _post_tracks(token["access_token"], audio_path, title, description, tags)
    if resp.status_code == 401:
        token = _refresh_and_save(token)  # raises SoundCloudAuthError if refresh fails
        resp = _post_tracks(token["access_token"], audio_path, title, description, tags)
    if resp.status_code not in (200, 201):
        time.sleep(5)
        resp = _post_tracks(token["access_token"], audio_path, title, description, tags)
    if resp.status_code not in (200, 201):
        raise SoundCloudAPIError(
            f"Upload failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    return resp.json().get("permalink_url", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add soundcloud_client.py tests/test_soundcloud_client.py && git commit -m "feat: soundcloud_client.upload_track with 401 refresh + one retry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `soundcloud_publish.py` CLI

**Files:**
- Create: `soundcloud_publish.py`
- Test: `tests/test_soundcloud_publish.py`

**Interfaces:**
- Consumes: `soundcloud_client.ensure_token`, `upload_track`, `save_app_credentials`, `run_oauth_flow`, `save_token`, `load_app_credentials`, `SoundCloudAuthError`, `SoundCloudAPIError`, `MAX_UPLOAD_SECONDS`; `clipboard_and_notify.notify`.
- Produces: the Stage-2 CLI. `main(argv) -> int` exit codes: 0 ok, 2 input problems (incl. duration > 24 h), 3 ffmpeg missing/failed, 4 auth failure, 5 upload failure. Functions `extract_audio(movie_path, out_path) -> Path`, `probe_duration_seconds(path) -> float`, `ffmpeg_available() -> bool`. Note: dry-run probes the source `.mov` directly with ffprobe (no extraction — deliberate simplification of the spec's wording).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_soundcloud_publish.py`:

```python
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import soundcloud_publish as sp


def _mk_inputs(td):
    movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_bytes(b"m")
    desc = Path(td) / "soundcloud_description.txt"; desc.write_text("D")
    return movie, desc


def _base_args(movie, desc):
    return ["--movie", str(movie), "--title", "T", "--description-file", str(desc)]


def test_missing_movie_exits_2():
    with tempfile.TemporaryDirectory() as td:
        _, desc = _mk_inputs(td)
        rc = sp.main(["--movie", str(Path(td) / "nope.mov"), "--title", "T",
                      "--description-file", str(desc)])
        assert rc == 2


def test_ffmpeg_missing_exits_3_with_install_hint(capsys=None):
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=False):
            rc = sp.main(_base_args(movie, desc))
        assert rc == 3


def test_dry_run_probes_and_never_uploads():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=3600.0), \
             mock.patch.object(sp, "extract_audio") as ex, \
             mock.patch.object(sp.soundcloud_client, "upload_track") as up:
            rc = sp.main(_base_args(movie, desc) + ["--dry-run"])
        assert rc == 0
        assert ex.call_count == 0
        assert up.call_count == 0


def test_duration_over_24h_exits_2():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=25 * 3600.0):
            rc = sp.main(_base_args(movie, desc) + ["--dry-run"])
        assert rc == 2


def test_real_run_extracts_uploads_notifies():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        fake_mp3 = Path(td) / "out.mp3"; fake_mp3.write_bytes(b"a")
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=3600.0), \
             mock.patch.object(sp, "extract_audio", return_value=fake_mp3) as ex, \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               return_value="https://sc/u/t") as up, \
             mock.patch.object(sp, "notify") as note:
            rc = sp.main(_base_args(movie, desc))
        assert rc == 0
        assert ex.call_count == 1
        up.assert_called_once()
        assert up.call_args.kwargs.get("title") or up.call_args.args[1] == "T"
        assert note.call_count == 1


def test_auth_error_exits_4_upload_error_exits_5():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        fake_mp3 = Path(td) / "out.mp3"; fake_mp3.write_bytes(b"a")
        base = _base_args(movie, desc)
        common = [
            mock.patch.object(sp, "ffmpeg_available", return_value=True),
            mock.patch.object(sp, "probe_duration_seconds", return_value=60.0),
            mock.patch.object(sp, "extract_audio", return_value=fake_mp3),
            mock.patch.object(sp, "notify"),
        ]
        with common[0], common[1], common[2], common[3], \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               side_effect=sp.soundcloud_client.SoundCloudAuthError("x")):
            assert sp.main(base) == 4
        with common[0], common[1], common[2], common[3], \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               side_effect=sp.soundcloud_client.SoundCloudAPIError("x")):
            assert sp.main(base) == 5


def test_ffmpeg_command_construction():
    with mock.patch.object(sp.subprocess, "run") as m:
        sp.extract_audio("/in/x.mov", "/out/x.mp3")
    cmd = m.call_args.args[0]
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert "320k" in cmd
    assert cmd[-1] == "/out/x.mp3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: new tests ERROR with `ModuleNotFoundError: No module named 'soundcloud_publish'`.

- [ ] **Step 3: Implement**

Create `soundcloud_publish.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add soundcloud_publish.py tests/test_soundcloud_publish.py && git commit -m "feat: soundcloud_publish CLI — ffmpeg extract + upload with dry-run and setup

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: `send_label_email.py` — SMTP send for "send" mode

**Files:**
- Create: `send_label_email.py`
- Test: `tests/test_send_label_email.py`

**Interfaces:**
- Consumes: nothing project-internal.
- Produces: CLI `python3 send_label_email.py --to ADDR --subject S --body-file F` (exit 0 sent, 2 config/input problem, 4 auth rejected, 5 send failed) and `--save-config` for one-time setup. Functions: `load_config(path=None) -> dict | None`, `save_config(address, app_password, path=None)`, `build_message(from_addr, to_addr, subject, body) -> EmailMessage` (raises `ValueError` on multiple recipients), `send(msg, config)`. Config at `~/.tracklist_secrets/gmail_smtp.json` (600).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_send_label_email.py`:

```python
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import send_label_email as sle


def test_load_config_missing_returns_none():
    with tempfile.TemporaryDirectory() as td:
        assert sle.load_config(path=Path(td) / "nope.json") is None


def test_config_roundtrip_and_mode_600():
    import os
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sec" / "gmail_smtp.json"
        sle.save_config("me@gmail.com", "abcd efgh", path=p)
        cfg = sle.load_config(path=p)
        assert cfg == {"address": "me@gmail.com", "app_password": "abcd efgh"}
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"


def test_build_message_fields():
    msg = sle.build_message("me@gmail.com", "label@x.com", "Subj", "Body text")
    assert msg["From"] == "me@gmail.com"
    assert msg["To"] == "label@x.com"
    assert msg["Subject"] == "Subj"
    assert "Body text" in msg.get_content()


def test_build_message_rejects_multiple_recipients():
    for bad in ("a@x.com,b@y.com", "a@x.com; b@y.com"):
        try:
            sle.build_message("me@g.com", bad, "s", "b")
            assert False, "should have raised"
        except ValueError:
            pass


def test_send_uses_ssl_login_and_send_message():
    cfg = {"address": "me@gmail.com", "app_password": "pw"}
    msg = sle.build_message(cfg["address"], "label@x.com", "s", "b")
    with mock.patch.object(sle.smtplib, "SMTP_SSL") as cls:
        smtp = cls.return_value.__enter__.return_value
        sle.send(msg, cfg)
    cls.assert_called_once_with("smtp.gmail.com", 465, timeout=30)
    smtp.login.assert_called_once_with("me@gmail.com", "pw")
    smtp.send_message.assert_called_once_with(msg)


def test_main_without_config_exits_2():
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(sle, "CONFIG_PATH", Path(td) / "nope.json"):
            rc = sle.main(["--to", "a@b.com", "--subject", "s", "--body-file", "/dev/null"])
        assert rc == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: new tests ERROR with `ModuleNotFoundError: No module named 'send_label_email'`.

- [ ] **Step 3: Implement**

Create `send_label_email.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add send_label_email.py tests/test_send_label_email.py && git commit -m "feat: send_label_email SMTP sender for auto-send mode

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Update the `label-emailer` agent — path fix, allowlist wording, send mode

**Files:**
- Modify: `.claude/agents/label-emailer.md`

**Interfaces:**
- Consumes: `~/.tracklist_secrets/outreach_mode.txt` (`draft`/`send`; missing = draft); Task 7's CLI is invoked by the *main session*, never by this agent.
- Produces: in draft mode, unchanged behavior. In send mode, the agent prints a fenced JSON block `[{"label","email","subject","body","source"}]` and does NOT create drafts and does NOT update the cache (the main session does both after confirmed sends).

- [ ] **Step 1: Fix the wrong project path (3 occurrences)**

In `.claude/agents/label-emailer.md`, replace every occurrence of
`~/Desktop/Track-ID-automation-main/label_outreach.py`:
- Line 16 (path list): `"$HOME/Desktop/TRACK ID PROJECT/label_outreach.py"`
- Lines 29 and 83 (shell commands): change `python3 ~/Desktop/Track-ID-automation-main/label_outreach.py` to `python3 "$HOME/Desktop/TRACK ID PROJECT/label_outreach.py"` (quotes are mandatory — the path contains spaces).

- [ ] **Step 2: Add mode awareness to Step A (pre-flight)**

After the existing ask-text check in Step A, add:

```markdown
2. `Read` `~/.tracklist_secrets/outreach_mode.txt`. If missing or unreadable, MODE is `draft`.
   If its first word is `send`, MODE is `send`. Any other content: MODE is `draft`.
```

- [ ] **Step 3: Make Step D and Step E mode-conditional**

In Step D, after the compose instructions (item 14), replace item 15-16 with:

```markdown
15. **If MODE is `draft`:** call `mcp__claude_ai_Gmail__create_draft` with:
    - `to`: the resolved email address, plain string (never the obfuscated form).
    - `subject` / `body`: the strings composed above.
    Record `DRAFT_CREATED` on success, else `DRAFT_API_ERROR` with the error in Notes.
16. **If MODE is `send`:** do NOT call create_draft. Record status `COMPOSED` and keep
    the composed `{label, email, subject, body, source}` for the final output.
```

At the top of Step E add:

```markdown
**If MODE is `send`, SKIP Step E entirely** — the main session updates the cache only
after each email is actually sent.
```

- [ ] **Step 4: Make the Step F report mode-aware**

Replace Step F's item 21 with:

```markdown
21. **If MODE is `draft`:** after the table, print one line: `Done. Open Gmail → Drafts to review and send.`
21b. **If MODE is `send`:** after the table, print a fenced ```json code block containing the
    list of composed emails: `[{"label": ..., "email": ..., "subject": ..., "body": ..., "source": ...}]`.
    Print nothing after the JSON block. The main session will show the user the recipient
    list, get explicit confirmation, send via send_label_email.py, and update the cache.
```

- [ ] **Step 5: Sharpen the allowlist wording**

- In the frontmatter `description` and the intro paragraph, replace "whitelist `waterhousestudios` from YouTube Content ID claims" with "add the channel `waterhousestudios` to their YouTube Content ID allowlist (promotional use only, not monetized)".
- In Step D item 14, the guidance sentence for sentences 2-3 becomes: `Sentences 2-3 (if any) should be brief and lead naturally into the ask — the ask is that they add the channel to their Content ID allowlist. Do not gush, do not flatter.`

- [ ] **Step 6: Verify**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && grep -c "Track-ID-automation-main" .claude/agents/label-emailer.md; grep -c "outreach_mode" .claude/agents/label-emailer.md; grep -c "allowlist" .claude/agents/label-emailer.md
```
Expected: `0`, then `>=2`, then `>=2`. Also run `python3 tests/run_all.py` — still all green (no code touched).

- [ ] **Step 7: Commit**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add .claude/agents/label-emailer.md && git commit -m "fix: label-emailer path bug; add send-mode + allowlist wording

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Rewrite `~/.claude/commands/deploy-content.md` — four-stage orchestration

**Files:**
- Modify: `/Users/waterhousestudios/.claude/commands/deploy-content.md` (full rewrite — lives OUTSIDE the repo, no git commit for this file; the repo copy of record is added in this task)
- Create: `docs/deploy-content-command.md` (repo copy of the same content, committed, so the command is versioned)

**Interfaces:**
- Consumes: everything from Tasks 1–8; `deploy_output/` dir convention `~/Desktop/deploy_output`.
- Produces: the user-facing workflow.

- [ ] **Step 1: Write the new command file**

Replace the entire contents of `~/.claude/commands/deploy-content.md` with:

````markdown
---
description: Deploy the latest DJ stream — tracklist build, SoundCloud upload, YouTube publish, label outreach
allowed-tools: Bash, Read, Agent
---

The user invoked "deploy content". Run four stages in order. A failed stage NEVER blocks
later stages — note the failure and continue. Finish with a one-line-per-stage summary.
The project lives at `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/` (path has
spaces — always quote it). Output dir: `~/Desktop/deploy_output`.
Honor natural-language skips: "skip soundcloud", "skip youtube", "skip emails".

## Stage 0 — Preflight

```bash
test -f ~/.tracklist_secrets/soundcloud.json && echo SC_OK || echo SC_SETUP_NEEDED
which ffmpeg >/dev/null && echo FFMPEG_OK || echo FFMPEG_MISSING
```

- If FFMPEG_MISSING: tell the user to run `! brew install ffmpeg`, wait for them.
- If SC_SETUP_NEEDED: first-time SoundCloud connect must run interactively. Tell the user
  to run: `! python3 "$HOME/Desktop/TRACK ID PROJECT/soundcloud_publish.py" --setup`
  They'll need a SoundCloud app registered at soundcloud.com/you/apps (Artist Pro required)
  with redirect URI exactly `http://localhost:8766/callback`. Wait until it succeeds.

## Stage 1 — Tracklist build

Dry-run preview first:

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && python3 post_tracklist.py --dry-run --skip-mixcloud
```

Show the user the description, stream-start datetime, filtered-track count, chapter count.
Flag anything suspicious (0-1 chapters, many pre-stream skips, odd start time).
Ask: "Looks right — deploy?" Wait for confirmation, then (10-minute Bash timeout —
Songlink pacing makes a 30-track set take ~3.5 min):

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && python3 post_tracklist.py --skip-mixcloud --write-descriptions ~/Desktop/deploy_output
```

This writes `~/Desktop/deploy_output/{youtube_description.txt,soundcloud_description.txt,run_meta.json}`
and copies the YouTube description to the clipboard (fallback for manual pasting).

## Stage 2 — SoundCloud upload

Read the title and movie path from `~/Desktop/deploy_output/run_meta.json`. Preview:

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && python3 soundcloud_publish.py --dry-run \
  --movie "<movie_path from run_meta>" --title "<title from run_meta>" \
  --description-file ~/Desktop/deploy_output/soundcloud_description.txt
```

Show duration, estimated size, title. Ask go/no-go. On go (10-minute Bash timeout):
same command without `--dry-run`. Report the returned track URL.
Exit codes: 2 input, 3 ffmpeg, 4 auth (suggest `--setup` re-run), 5 upload.

## Stage 3 — YouTube publish (browser)

Ask the user: **"Did you stream this set live to YouTube?"**

- **Yes:** the video is already on the channel. Load the Claude-in-Chrome tools, open
  `studio.youtube.com` → Content → the newest video → Details. Set the description to the
  contents of `~/Desktop/deploy_output/youtube_description.txt`. Save and VERIFY the save
  actually happened before reporting success.
- **No:** ask "Public or Unlisted?". Then upload the `.mov` (path from `run_meta.json`)
  through YouTube Studio: Create → Upload videos → file upload. Set title (from
  `run_meta.json`), description (from the file), chosen visibility. Warn the user first:
  Chrome must stay open until upload + processing finish.
- Any browser failure: report the exact failing step, remind the user the description is
  on the clipboard for manual pasting, and continue to Stage 4.

## Stage 4 — Label outreach

```bash
cat ~/.tracklist_secrets/outreach_mode.txt 2>/dev/null || echo draft
```

Dispatch the label-emailer agent: `Agent({subagent_type: "label-emailer", prompt: "Process the latest session in tracklist_live.txt"})`.

- **draft mode:** relay the agent's report table. Remind: Gmail → Drafts → review → send.
- **send mode:** the agent returns a JSON list of composed emails. Show the user a table
  (label → email → subject) and ask ONE explicit go/no-go for the whole batch. On go, for
  each email: write the body to a temp file, then
  `python3 "$HOME/Desktop/TRACK ID PROJECT/send_label_email.py" --to <email> --subject <subject> --body-file <tmp>`.
  Collect successes, then mark them contacted in ONE call by piping
  `[{"name","email","source"}]` JSON to
  `python3 "$HOME/Desktop/TRACK ID PROJECT/label_outreach.py" --action mark-contacted --cache ~/.tracklist_secrets/contacted_labels.json --labels-stdin`.
  If SMTP auth fails (exit 4): stop sending, tell the user, and fall back to reporting
  the composed emails so nothing is lost.
- If the agent reports the ask-text file is missing, tell the user it must be written
  first (offer to draft it together) and mark the stage skipped.

## Final summary

One line per stage: `Stage N — done/skipped/failed(reason)`. If Stage 3 saved a
description, remind the user to double-check it on the video page.
````

- [ ] **Step 2: Copy into the repo and verify**

```bash
cp "$HOME/.claude/commands/deploy-content.md" "$HOME/Desktop/TRACK ID PROJECT/docs/deploy-content-command.md"
grep -c "skip-mixcloud" "$HOME/.claude/commands/deploy-content.md"
```
Expected: grep prints `2` (both post_tracklist invocations pass `--skip-mixcloud`).

- [ ] **Step 3: Commit the repo copy**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git add docs/deploy-content-command.md && git commit -m "docs: deploy-content v2 command — 4-stage orchestration (repo copy)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Setup assets, full-suite verification, and first-run checklist

**Files:**
- Create: `~/.tracklist_secrets/outreach_mode.txt`, `~/.tracklist_secrets/label_email_ask.txt` (both outside repo)
- Verify: `.gitignore`

**Interfaces:**
- Consumes: everything above.
- Produces: a runnable system. Several steps are interactive — do them WITH the user in-session.

- [ ] **Step 1: Default outreach mode**

```bash
echo draft > ~/.tracklist_secrets/outreach_mode.txt && chmod 600 ~/.tracklist_secrets/outreach_mode.txt
```

- [ ] **Step 2: Draft the ask text with the user**

Draft this content, show it to the user, iterate until they approve, then save to
`~/.tracklist_secrets/label_email_ask.txt` (chmod 600). Starting draft:

```text
I'd like to ask a small favour: could you add my YouTube channel, waterhousestudios,
to your Content ID allowlist? The streams are strictly promotional — never monetized —
and every track is credited in the description with store links. If you'd ever prefer
a track of yours removed instead, tell me and it's gone the same day. Thank you for
the music.
```

**Do not save without explicit user approval of the wording.**

- [ ] **Step 3: Verify secrets are gitignored**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && cat .gitignore && git status --short
```
Expected: `.tracklist_secrets` is irrelevant here (it's in `$HOME`, not the repo) — confirm `git status` shows NO secret-looking files. If any appear, stop and fix `.gitignore` before anything else.

- [ ] **Step 4: Full test suite**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && python3 tests/run_all.py
```
Expected: `N/N passed.` with zero failures.

- [ ] **Step 5: Interactive setup (with the user)**

1. `! brew install ffmpeg` (if Stage-0 preflight said missing)
2. Confirm the user's SoundCloud plan is Artist Pro (Settings → Subscriptions). If it
   isn't, STOP and discuss (upgrade vs. browser-upload fallback) before registering.
3. `! python3 "$HOME/Desktop/TRACK ID PROJECT/soundcloud_publish.py" --setup`

- [ ] **Step 6: Manual first-run protocol (from the spec — do not skip)**

1. Pick a short test recording (2-3 tracks with clearly resolvable labels).
2. Run `/deploy-content` end-to-end.
3. Verify: SoundCloud track is live and plays; description shows timestamps; YouTube
   description saved on the right video; exactly one Gmail draft per DRAFT_CREATED row;
   each draft contains the ask text verbatim and the correct tracks.
4. Anything wrong: delete the drafts / uploads, fix, repeat before any real run.

- [ ] **Step 7: Push**

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && git push origin main
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** Stage 1 → Tasks 1-3; Stage 2 → Tasks 4-6; Stage 3 → Task 9 (browser steps are command instructions, per spec); Stage 4 → Tasks 7-8 + command Stage 4; setup/first-run → Task 10. Error-handling table rows map to: ffmpeg (T6 exit 3), refresh-fail (T5), size/duration limits (T5/T6), retry-once-after-5s (T5), browser failure (T9 Stage 3), ask-text missing (existing agent behavior, T9 Stage 4), mode missing = draft (T8), SMTP fail fallback (T9 Stage 4), stage independence (T9 preamble).
- **Deliberate spec deviation (documented):** dry-run probes the source `.mov` with ffprobe instead of extracting audio first — same information, less work.
- **Type consistency:** `upload_track` returns `str` (permalink) everywhere; token dict `{access_token, refresh_token}` consistent across Tasks 4-5-6; `run_meta.json` keys consistent across Tasks 3 and 9.
