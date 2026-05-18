# BLT Tracklist Logging — Design Spec
**Date:** 2026-05-17

## Goal

Automatically log every track played to the crowd during a DJ set, in real time, using Beat Link Trigger (BLT) monitoring the CDJ 3000s over the local network.

## Setup

- 2× Pioneer CDJ 3000 — connected via ethernet to TP-Link LS1005G switch
- Allen & Heath Xone:96 — analog mixer, not network-connected
- Mac — connected via ethernet to the same switch (IP: 192.168.0.146)
- Beat Link Trigger v8.0.0 — installed on Mac

## What "Playing to the Crowd" Means

The Xone:96 is analog and has no network connection, so BLT cannot detect fader position. Instead we use the **master player** as a proxy — the CDJ that is the tempo master is almost always the track playing to the crowd.

A track is logged when it becomes the master player's current track.

## Architecture

```
CDJ 3000s  →  Pro DJ Link (ethernet)  →  Beat Link Trigger
                                               ↓
                                    writes to tracklist_live.txt
                                               ↓
                                    Python scripts (after the set)
                                               ↓
                                    formatted tracklist with links
```

## Output File

**Location:** `~/Desktop/tracklist_live.txt`

**Format** (matches existing `tracklist_parser.py`):
```
─── Session started 2026-05-17 22:34:00 ───
22:34:15  [Player 3]  Aaliyah — Try Again
22:58:42  [Player 1]  Daft Punk — One More Time
```

- Session header written once when BLT starts logging
- One line per track, written the moment it becomes master
- Player number, artist, and title come from Pro DJ Link metadata
- File is appended to (not overwritten) so multiple sessions accumulate

## BLT Configuration

Two Clojure expressions are pasted into BLT — the user never edits them again:

1. **Global Setup Expression** — fires when BLT opens. Writes the `─── Session started ───` header line to the file.

2. **Trigger Tracked Update Expression** — fires on every status packet from the master player. Uses `locals` atom state to write exactly one line per new track. Waits briefly for metadata's artist `SearchableItem` to populate (artist label is accessed via `.label` field, not `.getLabel` method, since `org.deepsymmetry.beatlink.data.SearchableItem` has no such getter).

**Trigger settings:**
- Watch: Master Player
- Enabled: Always

**Note:** The Activation Expression is NOT used — it only fires once when the trigger first activates, not on each track change within an active session.

## Python Scripts (unchanged)

After the set, the user runs:
```
python3 ~/Desktop/TRACK ID PROJECT/tracklist_format.py ~/Desktop/tracklist_live.txt
```

The existing `tracklist_parser.py` reads the file as-is. No changes needed to the Python scripts.

## What's Out of Scope

- Step 2 (Discogs/Bandcamp lookups) — handled by existing scripts, covered separately
- Multi-session management — file appends, sessions are separated by headers
- Tracks cued in headphones but never played to the crowd — excluded by design (master player only)
