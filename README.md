# DJ Tracklist Auto-Logger

**What it does:** Logs every track you play to the crowd from your CDJ 3000s in real time, then formats the list with Discogs links so you can paste it into YouTube/Mixcloud descriptions.

**Built:** 2026-05-17

---

## Your Setup

- **CDJs:** 2× Pioneer CDJ 3000, ethernet-connected to a TP-Link LS1005G switch
- **Mixer:** Allen & Heath Xone:96 (analog, not on the network — that's fine)
- **Mac:** Connected via ethernet to the same TP-Link switch
- **Beat Link Trigger v8.0.0:** Installed in `/Applications/Beat Link Trigger.app`
  - Auto-opens at login (configured in System Settings → Login Items)

---

## How to Use It (Every Set)

1. Plug everything in: CDJs, mixer, Mac on the switch
2. **Open Beat Link Trigger** (or let it open automatically at login)
   - It writes a new session header to `~/Desktop/tracklist_live.txt`
3. **DJ normally.** Every track that becomes the master player gets logged automatically
4. **After your set,** open Terminal and run:
   ```
   python3 "$HOME/Desktop/TRACK ID PROJECT/tracklist_format.py" ~/Desktop/tracklist_live.txt --out ~/Desktop/set.txt
   ```
5. **Open `~/Desktop/set.txt`** — formatted tracklist with timestamps + Discogs links

---

## Where Everything Lives

| File | What it is |
|------|-----------|
| `~/Desktop/tracklist_live.txt` | The live log file BLT writes to during your set |
| `~/Desktop/TRACK ID PROJECT/tracklist_parser.py` | Reads the log file and extracts each track |
| `~/Desktop/TRACK ID PROJECT/tracklist_lookup.py` | Looks up tracks on Discogs and Bandcamp |
| `~/Desktop/TRACK ID PROJECT/tracklist_format.py` | The main script you run after your set |
| `~/Desktop/TRACK ID PROJECT/blt_expressions/global_setup.clj` | Backup of BLT's session-header code |
| `~/Desktop/TRACK ID PROJECT/blt_expressions/tracked_update.clj` | Backup of BLT's track-logging code |
| `~/Desktop/TRACK ID PROJECT/tests/test_log_format.py` | Test that confirms the log format is readable |
| `~/Desktop/TRACK ID PROJECT/docs/superpowers/specs/` | Design spec (what we decided to build) |
| `~/Desktop/TRACK ID PROJECT/docs/superpowers/plans/` | Implementation plan (how we built it) |

---

## How BLT Knows What to Log

Inside Beat Link Trigger, two small pieces of code do the work:

1. **Global Setup Expression** — runs once when BLT opens. Writes a session header to `tracklist_live.txt`.
2. **Trigger 1 — Tracked Update Expression** — runs every time a new track becomes master on any CDJ. Writes one line: timestamp, player number, artist, title.

The trigger is set to:
- **Watch:** Master Player
- **Enabled:** Always

If you ever need to re-paste this code (e.g., reinstalled BLT), open the `.clj` files in `blt_expressions/` and copy their contents into the matching BLT editor.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| BLT doesn't see your CDJs | Make sure CDJs and Mac are all plugged into the same TP-Link switch |
| `tracklist_live.txt` has no entries after a set | Check that BLT was open during the set, and that you did `File → Save` in BLT after the original setup |
| Tracks show "Unknown Artist" | Track wasn't analyzed in rekordbox, OR you switched tracks faster than ~200ms before metadata loaded |
| Python script complains about `requests` | Run `pip3 install requests beautifulsoup4` once |

---

## Step 2 — Auto-Post to Mixcloud + YouTube (done 2026-05-17)

After each stream, run:

```
python3 "$HOME/Desktop/TRACK ID PROJECT/post_tracklist.py"
```

This:
1. Finds the newest `.mov` recording in `~/Movies/` to know when your stream started.
2. Reads `~/Desktop/tracklist_live.txt` (Step 1's output).
3. Filters out tracks that were master for less than 30 seconds.
4. Looks up Discogs + a Songlink universal URL for each track.
5. Posts a timestamped tracklist + description to your most recent **Mixcloud** cloudcast.
6. Copies a YouTube-chapter-formatted description to your clipboard — paste into YouTube Studio.

### First-time setup

The first time you run it, it walks you through:
1. Creating a Mixcloud app at `mixcloud.com/developers/create/` (Redirect URI: `http://localhost:8765/callback`). You paste the Client ID + Secret it gives you.
2. A browser OAuth login to grant the app access to your Mixcloud account.
3. Optional: pasting a Discogs token for faster lookups (free at `discogs.com/settings/developers`).

After that, every future run is one command.

### Flags

| Flag | Purpose |
|------|---------|
| `--movie PATH` | Override which recording's filename is used as t=0 |
| `--cloudcast SLUG` | Post to a specific cloudcast instead of the newest |
| `--log PATH` | Use a different tracklist log file |
| `--session N` | Pick a specific session from the log (default: latest) |
| `--dry-run` | Print what would post; don't touch Mixcloud or clipboard |
| `--skip-mixcloud` | Only build the YouTube clipboard |
| `--skip-youtube` | Only post to Mixcloud |

### Credentials

Live in `~/.tracklist_secrets/` (mode 700, files mode 600). Never commit this folder.
