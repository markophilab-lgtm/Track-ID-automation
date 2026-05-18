# BLT Tracklist Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Beat Link Trigger to automatically write a timestamped tracklist file whenever a new track becomes the master player, in a format the existing Python scripts can read.

**Architecture:** BLT watches the master CDJ over the local network. A Global Setup Expression writes a session header to `~/Desktop/tracklist_live.txt` when BLT opens. A Trigger Activation Expression appends one line per track when the master player loads a new track. No changes to existing Python scripts.

**Tech Stack:** Beat Link Trigger v8.0.0 (Clojure expressions), Python 3.9 (existing scripts, unchanged)

---

### Task 1: Save reference expression files to disk

**Files:**
- Create: `~/Desktop/TRACK ID PROJECT/blt_expressions/global_setup.clj`
- Create: `~/Desktop/TRACK ID PROJECT/blt_expressions/trigger_activation.clj`

These are backup copies. The real code lives inside BLT, but having these files means you can always re-paste them if BLT is reinstalled.

- [ ] **Step 1: Write global_setup.clj**

Save this exact content to `~/Desktop/TRACK ID PROJECT/blt_expressions/global_setup.clj`:

```clojure
(let [now       (java.time.LocalDateTime/now)
      fmt       (java.time.format.DateTimeFormatter/ofPattern "yyyy-MM-dd HH:mm:ss")
      timestamp (.format now fmt)
      header    (str "─── Session started " timestamp " ───\n")
      path      (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")]
  (spit path header :append true))
```

- [ ] **Step 2: Write trigger_activation.clj**

Save this exact content to `~/Desktop/TRACK ID PROJECT/blt_expressions/trigger_activation.clj`:

```clojure
(when track-metadata
  (let [now      (java.time.LocalDateTime/now)
        fmt      (java.time.format.DateTimeFormatter/ofPattern "HH:mm:ss")
        time-str (.format now fmt)
        player   (.getDeviceNumber status)
        title    (or (.getTitle track-metadata) "Unknown Title")
        artist-obj (.getArtist track-metadata)
        artist   (if artist-obj (.getLabel artist-obj) "Unknown Artist")
        line     (str time-str "  [Player " player "]  " artist " — " title "\n")
        path     (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")]
    (spit path line :append true)))
```

Note: `─` is the `─` box-drawing character. `—` is the `—` em dash. Both are required to match `tracklist_parser.py`'s regex patterns exactly.

- [ ] **Step 3: Verify both files exist**

Run: `ls ~/Desktop/TRACK ID PROJECT/blt_expressions/`

Expected output:
```
global_setup.clj
trigger_activation.clj
```

---

### Task 2: Write a format-verification test

**Files:**
- Create: `~/Desktop/TRACK ID PROJECT/tests/test_log_format.py`

Before touching BLT, write a test that checks whether a sample log file is correctly parsed by the existing scripts. This gives us a way to verify BLT output is correct once we set it up.

- [ ] **Step 1: Create tests directory**

Run: `mkdir -p ~/Desktop/TRACK ID PROJECT/tests`

- [ ] **Step 2: Write the test**

Save to `~/Desktop/TRACK ID PROJECT/tests/test_log_format.py`:

```python
import sys
sys.path.insert(0, "/Users/waterhousestudios/Desktop/TRACK ID PROJECT")

from tracklist_parser import parse_log

SAMPLE_LOG = """\
─── Session started 2026-05-17 22:00:00 ───
22:00:05  [Player 3]  Aaliyah — Try Again
22:04:12  [Player 1]  Daft Punk — One More Time
"""

def test_session_detected():
    sessions = parse_log(SAMPLE_LOG)
    assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

def test_track_count():
    sessions = parse_log(SAMPLE_LOG)
    assert len(sessions[0].tracks) == 2, f"Expected 2 tracks, got {len(sessions[0].tracks)}"

def test_first_track_artist():
    sessions = parse_log(SAMPLE_LOG)
    assert sessions[0].tracks[0].artist == "Aaliyah"

def test_first_track_title():
    sessions = parse_log(SAMPLE_LOG)
    assert sessions[0].tracks[0].title == "Try Again"

def test_second_track_artist():
    sessions = parse_log(SAMPLE_LOG)
    assert sessions[0].tracks[1].artist == "Daft Punk"

def test_player_field():
    sessions = parse_log(SAMPLE_LOG)
    assert sessions[0].tracks[0].player == "Player 3"

if __name__ == "__main__":
    failures = []
    tests = [test_session_detected, test_track_count, test_first_track_artist,
             test_first_track_title, test_second_track_artist, test_player_field]
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failures.append(t.__name__)
    if failures:
        print(f"\n{len(failures)} test(s) failed.")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests passed.")
```

- [ ] **Step 3: Run tests — verify they pass before touching BLT**

Run: `python3 ~/Desktop/TRACK ID PROJECT/tests/test_log_format.py`

Expected output:
```
  PASS  test_session_detected
  PASS  test_track_count
  PASS  test_first_track_artist
  PASS  test_first_track_title
  PASS  test_second_track_artist
  PASS  test_player_field

All 6 tests passed.
```

If any test fails here, the existing parser has a bug that must be fixed before proceeding.

---

### Task 3: Configure BLT — Global Setup Expression

This makes BLT write a session header to `tracklist_live.txt` every time it opens.

- [ ] **Step 1: Open the Global Setup Expression editor in BLT**

In Beat Link Trigger:
1. Click the **Triggers** menu at the top
2. Click **Edit Global Setup Expression**
3. A code editor window will open (it may already have some text or be empty)

- [ ] **Step 2: Paste the expression**

Select all existing text in the editor (Cmd+A) and delete it. Then paste the contents of `~/Desktop/TRACK ID PROJECT/blt_expressions/global_setup.clj`:

```clojure
(let [now       (java.time.LocalDateTime/now)
      fmt       (java.time.format.DateTimeFormatter/ofPattern "yyyy-MM-dd HH:mm:ss")
      timestamp (.format now fmt)
      header    (str "─── Session started " timestamp " ───\n")
      path      (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")]
  (spit path header :append true))
```

- [ ] **Step 3: Save and close**

Click **Save** (or press Cmd+S). Close the expression editor window.

- [ ] **Step 4: Verify the session header was written**

Run: `cat ~/Desktop/tracklist_live.txt`

Expected output (date/time will differ):
```
─── Session started 2026-05-17 17:45:00 ───
```

If the file doesn't exist or is empty, the expression has an error — re-open it and check for typos.

---

### Task 4: Configure BLT — Trigger

This makes BLT write a line every time a new track becomes the master player.

- [ ] **Step 1: Set the trigger to watch the Master Player**

In the main BLT window, find the **Watch** dropdown (currently says "Any Player"). Click it and select **Master Player**.

- [ ] **Step 2: Set Enabled to Always**

Find the **Enabled** dropdown (currently says "Never" with a red circle). Click it and select **Always**.

- [ ] **Step 3: Open the Activation Expression editor**

In the main BLT window, click the **gear icon** (⚙) on the left side of the trigger row. A menu will appear. Click **Edit Activation Expression**.

- [ ] **Step 4: Paste the activation expression**

Select all existing text (Cmd+A), delete it, then paste the contents of `~/Desktop/TRACK ID PROJECT/blt_expressions/trigger_activation.clj`:

```clojure
(when track-metadata
  (let [now      (java.time.LocalDateTime/now)
        fmt      (java.time.format.DateTimeFormatter/ofPattern "HH:mm:ss")
        time-str (.format now fmt)
        player   (.getDeviceNumber status)
        title    (or (.getTitle track-metadata) "Unknown Title")
        artist-obj (.getArtist track-metadata)
        artist   (if artist-obj (.getLabel artist-obj) "Unknown Artist")
        line     (str time-str "  [Player " player "]  " artist " — " title "\n")
        path     (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")]
    (spit path line :append true)))
```

- [ ] **Step 5: Save and close**

Click **Save** (or press Cmd+S). Close the expression editor.

---

### Task 5: End-to-end test

- [ ] **Step 1: Load a track on your CDJ and make it master**

Press play on one of your CDJs. It should become the master player (indicated by the master icon on the CDJ display).

- [ ] **Step 2: Check the log file**

Run: `cat ~/Desktop/tracklist_live.txt`

Expected output (details will match whatever track is loaded):
```
─── Session started 2026-05-17 22:34:00 ───
22:34:15  [Player 3]  Aaliyah — Try Again
```

If the line shows `Unknown Artist — Unknown Title`, the CDJ metadata isn't loading. This usually means the track is on USB and the CDJ needs a moment — wait 5 seconds and load the track again.

- [ ] **Step 3: Run the format verification test against the real file**

Run: `python3 ~/Desktop/TRACK ID PROJECT/tests/test_log_format.py`

Note: this test uses a hardcoded sample, not the real file. It confirms the parser format is correct regardless of what BLT produced.

- [ ] **Step 4: Run the full Python pipeline on the real log**

Run: `python3 ~/Desktop/TRACK ID PROJECT/tracklist_format.py ~/Desktop/tracklist_live.txt`

Expected: a formatted line per track with a timestamp. Discogs/Bandcamp lookups will show "(no Discogs)" and "(no Bandcamp)" for now — that's correct, Step 2 handles those.

---

### Task 6: Save BLT state

- [ ] **Step 1: Save BLT configuration**

In BLT: **File → Save**. This saves your trigger and expression setup so it reloads automatically next time you open BLT.

- [ ] **Step 2: Confirm setup is complete**

Run: `ls ~/Desktop/TRACK ID PROJECT/blt_expressions/ ~/Desktop/TRACK ID PROJECT/tests/ ~/Desktop/tracklist_live.txt`

Expected:
```
/Users/waterhousestudios/Desktop/TRACK ID PROJECT/blt_expressions/:
global_setup.clj    trigger_activation.clj

/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/:
test_log_format.py

/Users/waterhousestudios/Desktop/tracklist_live.txt
```
