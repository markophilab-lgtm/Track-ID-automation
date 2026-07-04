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
Ask: "Looks right — deploy? And who's the artist for this set?" (title format is
`<artist> @ WTHS Radio (D.M.Y)`; if they don't name one, omit --artist and the
fallback `waterhousestudios` is used). Wait for confirmation, then (10-minute Bash
timeout — Songlink pacing makes a 30-track set take ~3.5 min):

```bash
cd "$HOME/Desktop/TRACK ID PROJECT" && python3 post_tracklist.py --skip-mixcloud --artist "<artist>" --write-descriptions ~/Desktop/deploy_output
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
