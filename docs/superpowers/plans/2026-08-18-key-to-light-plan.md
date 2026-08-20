# Key-to-Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the master CDJ's track changes, recolor the running LEDfx effects to the color of that track's musical key on Newton's *Opticks* note→color wheel.

**Architecture:** A new `keylight/` package (4 focused modules + guarded facade) imported by the existing `cdj_logger.py`. The logger's existing ProDj instance feeds two callbacks: track metadata (includes the key string) and client status changes (includes master/play flags). Pure functions for key parsing and color math; one stateful tracker; one stdlib-only HTTP client for the LEDfx REST API.

**Tech Stack:** Python 3 stdlib only (`urllib.request`, `json`, `colorsys`, `unittest`). No pip installs — the venue Mac mini must run this with plain `python3`.

**Spec:** `docs/superpowers/specs/2026-08-18-key-to-light-design.md`

## Global Constraints

- Stdlib only. No `requests`, no `pytest` — tests use `unittest`, run with `python3 -m unittest`.
- All new code lives in `keylight/` next to `prodj/`; tests in `tests/`.
- Tracklist logging must never break: every keylight entry point is wrapped by the guarded dispatch in `keylight/__init__.py` (Task 5). Modules may raise internally; only the facade swallows.
- LEDfx REST API base URL: `http://127.0.0.1:8888`, HTTP timeout 2.0 s.
- Pitch class convention everywhere: integer 0–11, C=0, C#=1 … B=11.
- Working directory `~` on the dev Mac is NOT a git repo. Commit steps apply only when working inside the Track-ID-automation repo (venue Mac mini) — otherwise skip them; do not `git init` anything.
- prodj facts (verified against `prodj/` source, do not re-derive):
  - metadata callback signature: `on_track(request, source_player, slot, item_id, reply)`; `reply` is a dict that includes `"key"` (string) alongside artist/title/album.
  - `ProDj.set_client_change_callback(cb)` — `cb(player_number)` is called with ONE argument on every status change of a known client.
  - `p.cl.getClient(player_number)` returns a client object with `.state` (list of strings that may contain `"master"`, `"play"`, `"on_air"`, `"sync"`), `.track_id` (int), `.play_state` (str, e.g. `"playing"`), `.key` (live key string from CDJ-3000 status packets, may be None), `.type` (`"cdj"`/`"djm"`).

---

### Task 1: `keylight/keys.py` — key string parser

**Files:**
- Create: `keylight/__init__.py` (empty for now; Task 5 fills it)
- Create: `keylight/keys.py`
- Test: `tests/test_keylight_keys.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `parse_key(text: str | None) -> tuple[int, bool] | None` — `(pitch_class 0-11 with C=0, is_minor)`, `None` if unparseable. Used by Tasks 5–6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keylight_keys.py
import unittest
from keylight.keys import parse_key


class TestClassicalNotation(unittest.TestCase):
    def test_major_keys(self):
        self.assertEqual(parse_key("C"), (0, False))
        self.assertEqual(parse_key("F#"), (6, False))
        self.assertEqual(parse_key("Bb"), (10, False))
        self.assertEqual(parse_key("Db"), (1, False))

    def test_minor_keys(self):
        self.assertEqual(parse_key("Am"), (9, True))
        self.assertEqual(parse_key("F#m"), (6, True))
        self.assertEqual(parse_key("Bbm"), (10, True))
        self.assertEqual(parse_key("Cmin"), (0, True))
        self.assertEqual(parse_key("A minor"), (9, True))

    def test_explicit_major_suffix(self):
        self.assertEqual(parse_key("Cmaj"), (0, False))
        self.assertEqual(parse_key("G major"), (7, False))

    def test_case_and_whitespace(self):
        self.assertEqual(parse_key(" am "), (9, True))
        self.assertEqual(parse_key("f#M"), (6, True))  # trailing m = minor


class TestCamelotNotation(unittest.TestCase):
    def test_majors(self):
        self.assertEqual(parse_key("8B"), (0, False))   # C
        self.assertEqual(parse_key("9B"), (7, False))   # G
        self.assertEqual(parse_key("1B"), (11, False))  # B
        self.assertEqual(parse_key("12B"), (4, False))  # E

    def test_minors(self):
        self.assertEqual(parse_key("8A"), (9, True))    # Am
        self.assertEqual(parse_key("1A"), (8, True))    # Abm
        self.assertEqual(parse_key("12A"), (1, True))   # Dbm/C#m

    def test_leading_zero_and_case(self):
        self.assertEqual(parse_key("08A"), (9, True))
        self.assertEqual(parse_key("08a"), (9, True))


class TestGarbage(unittest.TestCase):
    def test_unparseable(self):
        for bad in [None, "", "  ", "13B", "0A", "H", "Xm", "8", "AB", "8C"]:
            self.assertIsNone(parse_key(bad), f"expected None for {bad!r}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_keylight_keys -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'keylight'` (or ImportError on `parse_key`).

- [ ] **Step 3: Implement**

Create empty `keylight/__init__.py`, then:

```python
# keylight/keys.py
"""Parse rekordbox key strings (classical or Camelot) into (pitch_class, is_minor)."""

import re

# C=0 convention
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_CLASSICAL_RE = re.compile(
    r"^([A-Ga-g])\s*([#b]?)\s*(m|min|minor|maj|major)?$", re.IGNORECASE)
_CAMELOT_RE = re.compile(r"^0?(\d{1,2})\s*([ABab])$")


def parse_key(text):
    """Return (pitch_class 0-11, is_minor) or None if unparseable."""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None

    m = _CAMELOT_RE.match(s)
    if m:
        num = int(m.group(1))
        if not 1 <= num <= 12:
            return None
        # Camelot wheel steps in fifths; 8B = C major.
        pc_major = (7 * (num - 8)) % 12
        if m.group(2).upper() == "B":
            return (pc_major, False)
        # A = relative minor of same number (e.g. 8A = Am)
        return ((pc_major + 9) % 12, True)

    m = _CLASSICAL_RE.match(s)
    if m:
        pc = _LETTER_PC[m.group(1).upper()]
        if m.group(2) == "#":
            pc = (pc + 1) % 12
        elif m.group(2) == "b":
            pc = (pc - 1) % 12
        suffix = (m.group(3) or "").lower()
        is_minor = suffix in ("m", "min", "minor")
        return (pc, is_minor)

    return None
```

Note the classical regex only allows `#`/`b` accidentals (never both) and the
suffix group makes `"8C"` unmatchable by either pattern. `"A minor"` works
because the regex allows whitespace before the suffix.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_keylight_keys -v`
Expected: all PASS.

- [ ] **Step 5: Commit (only if inside the Track-ID repo)**

```bash
git add keylight/__init__.py keylight/keys.py tests/test_keylight_keys.py
git commit -m "feat(keylight): key string parser (classical + Camelot)"
```

---

### Task 2: `keylight/newton.py` — Newton wheel color mapping

**Files:**
- Create: `keylight/newton.py`
- Test: `tests/test_keylight_newton.py`

**Interfaces:**
- Consumes: pitch-class convention from Task 1.
- Produces (used by Tasks 5–6):
  - `color_for_key(pitch_class: int, is_minor: bool) -> str` — hex like `"#ff0000"`.
  - `gradient_for_key(pitch_class: int, is_minor: bool) -> str` — LEDfx CSS-style string `"linear-gradient(90deg, #.. 0%, #.. 50%, #.. 100%)"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keylight_newton.py
import unittest
from keylight.newton import color_for_key, gradient_for_key, HUES


class TestNewtonWheel(unittest.TestCase):
    def test_anchor_hues_follow_newton(self):
        # Newton (Opticks): D=red E=orange F=yellow G=green A=blue B=indigo C=violet
        self.assertEqual(HUES[2], 0)     # D red
        self.assertEqual(HUES[4], 30)    # E orange
        self.assertEqual(HUES[5], 60)    # F yellow
        self.assertEqual(HUES[7], 120)   # G green
        self.assertEqual(HUES[9], 240)   # A blue
        self.assertEqual(HUES[11], 275)  # B indigo
        self.assertEqual(HUES[0], 300)   # C violet

    def test_accidentals_interpolate_between_neighbors(self):
        self.assertEqual(HUES[3], 15)    # D# between D(0) and E(30)
        self.assertEqual(HUES[6], 90)    # F# between F(60) and G(120)
        self.assertEqual(HUES[8], 180)   # G# between G(120) and A(240)
        self.assertEqual(HUES[10], 258)  # A# between A(240) and B(275), rounded
        self.assertEqual(HUES[1], 330)   # C# between C(300) and D(360)

    def test_d_major_is_pure_red(self):
        self.assertEqual(color_for_key(2, False), "#ff0000")

    def test_all_24_keys_distinct(self):
        colors = {color_for_key(pc, minor)
                  for pc in range(12) for minor in (False, True)}
        self.assertEqual(len(colors), 24)

    def test_minor_is_darker_same_hue(self):
        major = color_for_key(9, False)  # A major: pure blue #0000ff
        minor = color_for_key(9, True)
        self.assertEqual(major, "#0000ff")
        self.assertNotEqual(major, minor)
        # darker: every RGB channel <= major's channel
        mj = [int(major[i:i+2], 16) for i in (1, 3, 5)]
        mn = [int(minor[i:i+2], 16) for i in (1, 3, 5)]
        self.assertTrue(all(a <= b for a, b in zip(mn, mj)))

    def test_gradient_format(self):
        g = gradient_for_key(2, False)
        self.assertTrue(g.startswith("linear-gradient(90deg, #"))
        self.assertIn(" 0%", g)
        self.assertIn(" 50%", g)
        self.assertIn(" 100%", g)
        self.assertIn("#ff0000 50%", g)  # key color at center


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_keylight_newton -v`
Expected: ImportError (module doesn't exist).

- [ ] **Step 3: Implement**

```python
# keylight/newton.py
"""Newton's Opticks note->color wheel, extended to all 24 keys.

Anchors (Newton): D=red E=orange F=yellow G=green A=blue B=indigo C=violet.
Accidentals get the hue midpoint of their white-key neighbors (C# uses D at
360 so violet wraps back to red, mirroring the spectral octave).
"""

import colorsys

# HSV hue in degrees, indexed by pitch class (C=0 .. B=11)
HUES = {
    0: 300,   # C  violet
    1: 330,   # C# violet->red midpoint
    2: 0,     # D  red
    3: 15,    # D# red->orange midpoint
    4: 30,    # E  orange
    5: 60,    # F  yellow
    6: 90,    # F# yellow->green midpoint
    7: 120,   # G  green
    8: 180,   # G# green->blue midpoint
    9: 240,   # A  blue
    10: 258,  # A# blue->indigo midpoint (257.5 rounded)
    11: 275,  # B  indigo
}

MINOR_SAT = 0.80
MINOR_VAL = 0.55
GRADIENT_SPREAD = 20  # degrees of hue either side of the key color


def _hsv_hex(hue_deg, sat, val):
    r, g, b = colorsys.hsv_to_rgb((hue_deg % 360) / 360.0, sat, val)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def color_for_key(pitch_class, is_minor):
    sat, val = (MINOR_SAT, MINOR_VAL) if is_minor else (1.0, 1.0)
    return _hsv_hex(HUES[pitch_class], sat, val)


def gradient_for_key(pitch_class, is_minor):
    sat, val = (MINOR_SAT, MINOR_VAL) if is_minor else (1.0, 1.0)
    hue = HUES[pitch_class]
    lo = _hsv_hex(hue - GRADIENT_SPREAD, sat, val)
    mid = _hsv_hex(hue, sat, val)
    hi = _hsv_hex(hue + GRADIENT_SPREAD, sat, val)
    return f"linear-gradient(90deg, {lo} 0%, {mid} 50%, {hi} 100%)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_keylight_newton -v`
Expected: all PASS.

- [ ] **Step 5: Commit (only if inside the Track-ID repo)**

```bash
git add keylight/newton.py tests/test_keylight_newton.py
git commit -m "feat(keylight): Newton wheel key->color mapping, 24 distinct keys"
```

---

### Task 3: `keylight/tracker.py` — master-deck state tracker

**Files:**
- Create: `keylight/tracker.py`
- Test: `tests/test_keylight_tracker.py`

**Interfaces:**
- Consumes: nothing from other modules (key strings pass through opaquely).
- Produces (used by Task 5): class `MasterTracker`:
  - `MasterTracker(on_change, debounce_s=2.0, clock=time.monotonic)` — `on_change(key_string)` fires when the room key should change.
  - `note_track(player_number: int, track_id: int, key_string: str | None)` — call when a deck loads a track (from metadata callback).
  - `note_status(player_number: int, is_master: bool, is_playing: bool, track_id: int)` — call on every status change.

Behavior (from spec): room follows the master deck; on master handoff or master's
track change, emit that track's key. No master → most recently *loaded* deck that
is playing. Missing/None key → hold current color (no emit). Debounce 2 s: an
emit within the debounce window is deferred, then delivered on the next event
after the window (CDJs send status ~5×/s, so delivery is prompt).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keylight_tracker.py
import unittest
from keylight.tracker import MasterTracker


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class TestMasterTracker(unittest.TestCase):
    def setUp(self):
        self.emitted = []
        self.clock = FakeClock()
        self.tr = MasterTracker(self.emitted.append, debounce_s=2.0,
                                clock=self.clock)

    def test_master_deck_key_emitted(self):
        self.tr.note_track(1, track_id=101, key_string="8A")
        self.tr.note_status(1, is_master=True, is_playing=True, track_id=101)
        self.assertEqual(self.emitted, ["8A"])

    def test_non_master_load_changes_nothing(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")   # cueing on deck 2
        self.tr.note_status(2, False, True, 202)
        self.assertEqual(self.emitted, ["8A"])

    def test_master_handoff_emits_new_key_after_debounce(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")
        self.clock.advance(5)
        self.tr.note_status(1, False, True, 101)
        self.tr.note_status(2, True, True, 202)
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_debounce_suppresses_flapping(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)          # emit 1: 8A
        self.tr.note_track(2, 202, "3B")
        self.tr.note_status(2, True, True, 202)           # within 2s: deferred
        self.tr.note_status(1, True, True, 101)           # flaps back
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(3)
        self.tr.note_status(1, True, True, 101)           # stable master after window
        self.assertEqual(self.emitted, ["8A"])            # same key: nothing new

    def test_deferred_emit_fires_after_window(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")
        self.tr.note_status(2, True, True, 202)           # deferred (within 2s)
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(3)
        self.tr.note_status(2, True, True, 202)           # next event delivers
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_no_master_falls_back_to_latest_loaded_playing(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, False, True, 101)
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(5)
        self.tr.note_track(2, 202, "3B")                  # loaded later
        self.tr.note_status(2, False, True, 202)
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_missing_key_holds_color(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_track(1, 102, None)                  # untagged track
        self.tr.note_status(1, True, True, 102)
        self.assertEqual(self.emitted, ["8A"])            # held

    def test_master_track_change_emits(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_track(1, 102, "10B")                 # new track same deck
        self.tr.note_status(1, True, True, 102)
        self.assertEqual(self.emitted, ["8A", "10B"])

    def test_same_key_not_re_emitted(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_status(1, True, True, 101)
        self.assertEqual(self.emitted, ["8A"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_keylight_tracker -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# keylight/tracker.py
"""Decides when the room key changes, following the master deck."""

import time
import logging

log = logging.getLogger("keylight")


class _Deck:
    __slots__ = ("track_id", "key", "loaded_at", "is_master", "is_playing")

    def __init__(self):
        self.track_id = 0
        self.key = None
        self.loaded_at = 0.0
        self.is_master = False
        self.is_playing = False


class MasterTracker:
    def __init__(self, on_change, debounce_s=2.0, clock=time.monotonic):
        self.on_change = on_change
        self.debounce_s = debounce_s
        self.clock = clock
        self.decks = {}
        self.current_key = None
        self.last_emit_at = None
        self.pending_key = None

    def _deck(self, n):
        if n not in self.decks:
            self.decks[n] = _Deck()
        return self.decks[n]

    def note_track(self, player_number, track_id, key_string):
        d = self._deck(player_number)
        d.track_id = track_id
        d.key = key_string
        d.loaded_at = self.clock()
        self._evaluate()

    def note_status(self, player_number, is_master, is_playing, track_id):
        d = self._deck(player_number)
        d.is_master = is_master
        d.is_playing = is_playing
        if track_id and track_id != d.track_id:
            # status shows a track we never got metadata for
            d.track_id = track_id
            d.key = None
        self._evaluate()

    def _controlling_deck(self):
        masters = [d for d in self.decks.values() if d.is_master]
        if masters:
            return masters[0]
        playing = [d for d in self.decks.values() if d.is_playing]
        if playing:
            return max(playing, key=lambda d: d.loaded_at)
        return None

    def _evaluate(self):
        deck = self._controlling_deck()
        if deck is None:
            return
        key = deck.key
        if key is None:
            log.info("controlling deck has no key tag; holding color")
            return
        now = self.clock()
        in_window = (self.last_emit_at is not None
                     and now - self.last_emit_at < self.debounce_s)

        if in_window:
            if key != self.current_key:
                self.pending_key = key
            else:
                self.pending_key = None
            return

        # window is open: emit if the controlling deck's key differs
        candidate = key
        self.pending_key = None
        if candidate != self.current_key:
            self.current_key = candidate
            self.last_emit_at = now
            self.on_change(candidate)
```

Note on the debounce: while inside the window we only *record* the latest
differing key as pending; nothing fires. Once the window has passed, the next
event (status packets arrive ~5×/s) re-evaluates and emits if the controlling
deck's key still differs from what the room shows. A flap that returns to the
current key cancels the pending change (`pending_key = None` branch).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_keylight_tracker -v`
Expected: all PASS.

- [ ] **Step 5: Commit (only if inside the Track-ID repo)**

```bash
git add keylight/tracker.py tests/test_keylight_tracker.py
git commit -m "feat(keylight): master-deck tracker with debounce and fallbacks"
```

---

### Task 4: `keylight/ledfx.py` — LEDfx REST client

**Files:**
- Create: `keylight/ledfx.py`
- Test: `tests/test_keylight_ledfx.py`

**Interfaces:**
- Consumes: hex color + gradient strings (formats from Task 2).
- Produces (used by Task 5): class `LedfxClient`:
  - `LedfxClient(base_url="http://127.0.0.1:8888", timeout=2.0, dry_run=False, opener=None)` — `opener(request, timeout)` defaults to `urllib.request.urlopen`; injectable for tests.
  - `apply_key_color(color_hex: str, gradient: str) -> int` — recolors every active virtual's effect, returns number of virtuals updated. Raises on network failure (facade catches).

Color-swap rule (from spec): in each effect's existing config, replace only
values that *look like colors* — strings starting with `#` or
`linear-gradient(` — and skip any key whose name starts with `background`.
Gradient-looking values get the new gradient; plain colors get the hex.
Everything else (effect type, speed, blur, booleans like `flip_gradient`) is
preserved untouched.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keylight_ledfx.py
import json
import unittest
from keylight.ledfx import LedfxClient


class FakeOpener:
    """Collects requests; serves canned GET responses."""

    def __init__(self, virtuals_payload):
        self.virtuals_payload = virtuals_payload
        self.puts = []  # (url, payload dict)

    def __call__(self, request, timeout):
        url = request.full_url
        method = request.get_method()
        if method == "GET" and url.endswith("/api/virtuals"):
            return _Resp(self.virtuals_payload)
        if method == "PUT":
            self.puts.append((url, json.loads(request.data.decode())))
            return _Resp({"status": "success"})
        raise AssertionError(f"unexpected {method} {url}")


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


VIRTUALS = {
    "virtuals": {
        "strip-1": {
            "effect": {
                "type": "wavelength",
                "config": {
                    "gradient": "linear-gradient(90deg, #ff0000 0%, #0000ff 100%)",
                    "background_color": "#000000",
                    "flip_gradient": False,
                    "blur": 3.0,
                },
            }
        },
        "strip-2": {
            "effect": {
                "type": "scroll",
                "config": {
                    "color_lows": "#ff0000",
                    "color_mids": "#00ff00",
                    "color_high": "#0000ff",
                    "speed": 5,
                },
            }
        },
        "strip-idle": {"effect": {}},  # no active effect: skipped
    }
}


class TestLedfxClient(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener(VIRTUALS)
        self.client = LedfxClient(opener=self.opener)

    def test_updates_only_active_virtuals(self):
        n = self.client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        self.assertEqual(n, 2)
        self.assertEqual(len(self.opener.puts), 2)

    def test_gradient_and_colors_swapped_others_preserved(self):
        grad = "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)"
        self.client.apply_key_color("#123456", grad)
        by_url = dict(self.opener.puts)
        cfg1 = by_url["http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["config"]
        self.assertEqual(cfg1["gradient"], grad)
        self.assertEqual(cfg1["background_color"], "#000000")  # untouched
        self.assertEqual(cfg1["blur"], 3.0)
        self.assertEqual(cfg1["flip_gradient"], False)
        cfg2 = by_url["http://127.0.0.1:8888/api/virtuals/strip-2/effects"]["config"]
        self.assertEqual(cfg2["color_lows"], "#123456")
        self.assertEqual(cfg2["color_mids"], "#123456")
        self.assertEqual(cfg2["speed"], 5)

    def test_effect_type_preserved(self):
        self.client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        by_url = dict(self.opener.puts)
        self.assertEqual(
            by_url["http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["type"],
            "wavelength")

    def test_dry_run_sends_nothing(self):
        client = LedfxClient(dry_run=True, opener=self.opener)
        n = client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        self.assertEqual(n, 2)          # still counts what it would update
        self.assertEqual(self.opener.puts, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_keylight_ledfx -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# keylight/ledfx.py
"""Minimal LEDfx REST client: recolor active effects, preserve everything else."""

import json
import logging
import urllib.request

log = logging.getLogger("keylight")


def _default_opener(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


def _is_color(value):
    return isinstance(value, str) and (
        value.startswith("#") or value.startswith("linear-gradient("))


class LedfxClient:
    def __init__(self, base_url="http://127.0.0.1:8888", timeout=2.0,
                 dry_run=False, opener=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dry_run = dry_run
        self.opener = opener or _default_opener

    def _get(self, path):
        req = urllib.request.Request(self.base_url + path, method="GET")
        with self.opener(req, self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _put(self, path, payload):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT")
        with self.opener(req, self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _recolored(self, config, color_hex, gradient):
        new = dict(config)
        for k, v in config.items():
            if k.startswith("background"):
                continue
            if _is_color(v):
                new[k] = gradient if v.startswith("linear-gradient(") else color_hex
        return new

    def apply_key_color(self, color_hex, gradient):
        """Recolor all active virtuals. Returns count updated. Raises on I/O error."""
        data = self._get("/api/virtuals")
        updated = 0
        for vid, vdata in data.get("virtuals", {}).items():
            effect = vdata.get("effect") or {}
            etype = effect.get("type")
            config = effect.get("config")
            if not etype or not isinstance(config, dict):
                continue
            payload = {"type": etype,
                       "config": self._recolored(config, color_hex, gradient)}
            if self.dry_run:
                log.info("[dry-run] PUT /api/virtuals/%s/effects %s", vid, payload)
            else:
                self._put(f"/api/virtuals/{vid}/effects", payload)
            updated += 1
        return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_keylight_ledfx -v`
Expected: all PASS.

- [ ] **Step 5: Commit (only if inside the Track-ID repo)**

```bash
git add keylight/ledfx.py tests/test_keylight_ledfx.py
git commit -m "feat(keylight): LEDfx client that recolors active effects"
```

---

### Task 5: `keylight/__init__.py` — guarded facade

**Files:**
- Modify: `keylight/__init__.py` (currently empty)
- Test: `tests/test_keylight_facade.py`

**Interfaces:**
- Consumes: `parse_key` (Task 1), `color_for_key`/`gradient_for_key` (Task 2), `MasterTracker` (Task 3), `LedfxClient` (Task 4).
- Produces (used by Task 6): class `KeyLight`:
  - `KeyLight(prodj, dry_run=False)` — `prodj` is the live `ProDj` instance (used for `prodj.cl.getClient`).
  - `handle_metadata(source_player, reply)` — call from the logger's `on_track`. Never raises.
  - `handle_client_change(player_number)` — register as the client-change callback. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keylight_facade.py
import unittest
from keylight import KeyLight


class FakeClient:
    def __init__(self, state=(), track_id=0, play_state="playing", type="cdj"):
        self.state = list(state)
        self.track_id = track_id
        self.play_state = play_state
        self.type = type


class FakeCl:
    def __init__(self):
        self.clients = {}

    def getClient(self, n):
        return self.clients.get(n)


class FakeProdj:
    def __init__(self):
        self.cl = FakeCl()


class RecordingLedfx:
    def __init__(self):
        self.calls = []

    def apply_key_color(self, color_hex, gradient):
        self.calls.append((color_hex, gradient))
        return 1


class TestKeyLight(unittest.TestCase):
    def setUp(self):
        self.prodj = FakeProdj()
        self.kl = KeyLight(self.prodj, dry_run=True)
        self.kl.ledfx = RecordingLedfx()          # replace real client
        self.kl.tracker.debounce_s = 0.0          # no waiting in tests

    def test_full_flow_metadata_then_master_status(self):
        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.handle_metadata(1, {"track_id": 101, "key": "8A",
                                    "artist": "x", "title": "y"})
        self.kl.handle_client_change(1)
        self.assertEqual(len(self.kl.ledfx.calls), 1)
        color, gradient = self.kl.ledfx.calls[0]
        # 8A = A minor: pitch class 9, minor -> darker blue
        self.assertTrue(color.startswith("#"))
        self.assertTrue(gradient.startswith("linear-gradient("))

    def test_unknown_player_ignored(self):
        self.kl.handle_client_change(3)           # no such client
        self.assertEqual(self.kl.ledfx.calls, [])

    def test_djm_ignored(self):
        self.prodj.cl.clients[2] = FakeClient(type="djm")
        self.kl.handle_client_change(2)
        self.assertEqual(self.kl.ledfx.calls, [])

    def test_exceptions_are_swallowed(self):
        class Exploding:
            def apply_key_color(self, *a):
                raise RuntimeError("ledfx down")

        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.ledfx = Exploding()
        self.kl.handle_metadata(1, {"track_id": 101, "key": "8A"})
        self.kl.handle_client_change(1)           # must not raise
        # after failure, a repeat event retries (lazy retry)
        self.kl.ledfx = RecordingLedfx()
        self.kl.handle_client_change(1)
        self.assertEqual(len(self.kl.ledfx.calls), 1)

    def test_unparseable_key_no_call(self):
        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.handle_metadata(1, {"track_id": 101, "key": "??"})
        self.kl.handle_client_change(1)
        self.assertEqual(self.kl.ledfx.calls, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_keylight_facade -v`
Expected: ImportError on `KeyLight`.

- [ ] **Step 3: Implement**

```python
# keylight/__init__.py
"""Guarded facade wiring CDJ events to LEDfx colors.

Every public method is wrapped: exceptions are logged and swallowed so the
tracklist logger can never be broken by the light path.
"""

import logging

from keylight.keys import parse_key
from keylight.newton import color_for_key, gradient_for_key
from keylight.tracker import MasterTracker
from keylight.ledfx import LedfxClient

log = logging.getLogger("keylight")


def _guarded(fn):
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception:
            log.exception("keylight error (lights unchanged, logging unaffected)")
    return wrapper


class KeyLight:
    def __init__(self, prodj, dry_run=False):
        self.prodj = prodj
        self.ledfx = LedfxClient(dry_run=dry_run)
        self.tracker = MasterTracker(self._on_room_key)
        self._room_apply_failed_key = None

    # -- callbacks from cdj_logger ------------------------------------------

    @_guarded
    def handle_metadata(self, source_player, reply):
        key = reply.get("key") if isinstance(reply, dict) else None
        track_id = reply.get("track_id", 0) if isinstance(reply, dict) else 0
        parsed = parse_key(key)
        if key and not parsed:
            log.warning("unparseable key %r from player %s", key, source_player)
        self.tracker.note_track(source_player, track_id,
                                key if parsed else None)

    @_guarded
    def handle_client_change(self, player_number):
        c = self.prodj.cl.getClient(player_number)
        if c is None or getattr(c, "type", "") != "cdj":
            return
        state = getattr(c, "state", []) or []
        self.tracker.note_status(
            player_number,
            is_master="master" in state,
            is_playing=("play" in state
                        or getattr(c, "play_state", "") == "playing"),
            track_id=getattr(c, "track_id", 0))
        # lazy retry: if the last color apply failed, try again on any event
        if self._room_apply_failed_key is not None:
            key, self._room_apply_failed_key = self._room_apply_failed_key, None
            self._apply(key)

    # -- internal -----------------------------------------------------------

    def _on_room_key(self, key_string):
        self._apply(key_string)

    def _apply(self, key_string):
        parsed = parse_key(key_string)
        if not parsed:
            return
        pc, minor = parsed
        color = color_for_key(pc, minor)
        gradient = gradient_for_key(pc, minor)
        try:
            n = self.ledfx.apply_key_color(color, gradient)
            log.info("room key %s -> %s on %d virtuals", key_string, color, n)
        except Exception:
            self._room_apply_failed_key = key_string
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_keylight_facade -v`
Expected: all PASS. Also run the whole suite: `python3 -m unittest discover -s tests -p 'test_keylight*.py' -v` — all PASS.

- [ ] **Step 5: Commit (only if inside the Track-ID repo)**

```bash
git add keylight/__init__.py tests/test_keylight_facade.py
git commit -m "feat(keylight): guarded facade wiring CDJ events to LEDfx"
```

---

### Task 6: Wire into `cdj_logger.py`

**Files:**
- Modify: `cdj_logger.py` (callback wiring + CLI flags)

**Interfaces:**
- Consumes: `KeyLight` (Task 5).
- Produces: `--no-lights` and `--lights-dry-run` CLI flags; keylight events fed from the existing callbacks.

**Known quirk being fixed in passing:** the current code registers
`on_player_leave` as the *client change* callback, but that callback fires on
every status update, not on departure — so the "left network" print was wrong
anyway. We repurpose that slot for keylight and drop the misleading print.

- [ ] **Step 1: Make the edits**

Edit 1 — after `from prodj.core.prodj import ProDj` add:

```python
from keylight import KeyLight

keylight_instance = None
```

Edit 2 — at the end of `on_track(...)` (after the `f.write` line) add:

```python
    if keylight_instance:
        keylight_instance.handle_metadata(source_player, reply)
```

Edit 3 — replace the `on_player_leave` function with:

```python
def on_client_change(player_number):
    """Fires on every status update of a known client (not just departure)."""
    if keylight_instance:
        keylight_instance.handle_client_change(player_number)
```

Edit 4 — in `main()`, add the flags to the parser:

```python
    parser.add_argument("--no-lights", action="store_true",
                        help="Disable key-to-light (LEDfx) control")
    parser.add_argument("--lights-dry-run", action="store_true",
                        help="Log intended LEDfx calls without sending them")
```

Edit 5 — in `main()`, replace
`p.set_client_change_callback(on_player_leave)` with:

```python
    p.set_client_change_callback(on_client_change)

    global keylight_instance
    if not args.no_lights:
        keylight_instance = KeyLight(p, dry_run=args.lights_dry_run)
        mode = " (dry-run)" if args.lights_dry_run else ""
        print(f"  Key-to-light: ON{mode} — LEDfx at 127.0.0.1:8888")
    else:
        print("  Key-to-light: OFF (--no-lights)")
```

- [ ] **Step 2: Syntax check + full test suite**

Run: `python3 -m py_compile cdj_logger.py && python3 -m unittest discover -s tests -p 'test_keylight*.py'`
Expected: compiles, all tests PASS.

- [ ] **Step 3: Offline smoke test (no CDJs needed)**

Run: `python3 cdj_logger.py --lights-dry-run --out /tmp/smoke_tracklist.txt` for ~5 s, then Ctrl-C.
Expected: banner shows "Key-to-light: ON (dry-run)", no traceback, clean shutdown. (No CDJs on the network, so no events — this verifies imports and wiring only.)

- [ ] **Step 4: Commit (only if inside the Track-ID repo)**

```bash
git add cdj_logger.py
git commit -m "feat: wire keylight into CDJ logger (--no-lights, --lights-dry-run)"
```

---

### Task 7: Venue bring-up checklist (manual, at the Waterhouse)

No code. Run through in order on the Mac mini:

- [ ] Sync files to the mini: `keylight/` (5 files), `tests/` (5 test files), updated `cdj_logger.py`. `git fetch` first per repo workflow, then commit.
- [ ] `python3 -m unittest discover -s tests -p 'test_keylight*.py'` on the mini — all PASS.
- [ ] LEDfx running with your usual effects active; confirm `curl -s http://127.0.0.1:8888/api/virtuals | head -c 200` returns JSON.
- [ ] Start dry: `python3 cdj_logger.py --lights-dry-run`. Load a key-tagged track on a CDJ, press play, make it master. Expect a `[dry-run] PUT /api/virtuals/...` log line with a color.
- [ ] Restart without the flag: `python3 cdj_logger.py`. Same test — the room should take the track's key color while the effect keeps moving.
- [ ] Handoff test: play a second track on the other deck in a different key, let master hand over — color should follow within ~2 s of the handoff, not when the track was loaded.
- [ ] Kill LEDfx mid-run — logger must keep logging tracks with only a warning. Restart LEDfx — next track/master change recolors again (lazy retry).
- [ ] Untagged track (no key in rekordbox) — color holds, log notes the miss.

---

## Self-Review Notes

- **Spec coverage:** parser (Task 1), Newton wheel + accidentals + minor variant (Task 2), master-follows + debounce + fallbacks (Task 3), LEDfx recolor preserving effects + dry-run + timeout (Task 4), guarded dispatch + lazy retry + unparseable-key logging (Task 5), `--no-lights` + wiring (Task 6), venue E2E (Task 7). Out-of-scope items from the spec remain out.
- **Type consistency:** `parse_key` returns `(pc, is_minor) | None` and is consumed with exactly that shape in Task 5; `apply_key_color(color_hex, gradient) -> int` matches between Tasks 4 and 5; tracker callback carries the raw key string, parsed only at the facade boundary.
- **Placeholder scan:** clean — every step has runnable code or an exact command.
