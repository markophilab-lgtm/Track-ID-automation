# Key-to-Light — venue bring-up (Beat Link Trigger version)

The room takes the color of the master deck's musical key, on Newton's
*Opticks* wheel: D=red, E=orange, F=yellow, G=green, A=blue, B=indigo,
C=violet. Sharps/flats sit between their neighbors; minor keys are the same
color, darker.

## How it actually hooks up

The original plan assumed a Python `cdj_logger.py` using a `prodj` library.
That script lives on the other Mac — on this Mac mini the CDJs are read by
**Beat Link Trigger** (the "showtime" trigger, expressions stored in BLT's own
preferences and mirrored in `blt_expressions/`). So the wiring is:

```
CDJ  →  Beat Link Trigger (Tracked Update expression)  →  python3 -m keylight.cli "<key>"  →  LEDfx REST API
```

BLT decides *when* the room key changes (master deck, key actually changed,
2 s debounce). The Python side decides *what color* that key is and sends it.
The tracklist line is written **before** the light call, and the light call
runs on a background thread, so nothing about the lights can cost you a
tracklist entry or stall BLT.

## Install the expression (one time, ~2 minutes)

BLT is running as you read this, and it rewrites its preferences when it
quits — so this must be pasted through the UI, not edited on disk.

1. In Beat Link Trigger, first back up what you have: **File → Save** (or
   Triggers → Export) so you can get back to today's setup.
2. Open the trigger's **Tracked Update Expression** editor (the same one that
   currently writes `tracklist_live.txt`).
3. Replace its whole contents with `blt_expressions/tracked_update_with_lights.clj`
   from this repo. The logging half is byte-identical to what's in there now;
   the only addition is the key-to-light block at the bottom.
4. Set the trigger's **Enabled** to *Always* and leave **Players** as-is —
   the expression checks `isTempoMaster` itself.

## Bring-up checks, in order

- [ ] Tests on this machine: `python3 -m unittest discover -s tests -p 'test_keylight*.py'` → 39 pass.
- [ ] LEDfx running with your effects up: `curl -s http://127.0.0.1:8888/api/virtuals | head -c 200` returns JSON.
- [ ] Dry run, no lights touched: `python3 -m keylight.cli --dry-run "8A"` →
      prints `key 8A -> #00008c on N virtuals`.
- [ ] Live single shot, lights should turn red: `python3 -m keylight.cli "D"`.
      Then put your look back with your usual LEDfx scene.
- [ ] Paste the expression in (above), load a key-tagged track on a CDJ, play
      it, make it master → room takes that key's color within about a second.
- [ ] Handoff: play a different key on the other deck and hand master over →
      color follows the handoff, not the load.
- [ ] Kill LEDfx mid-set → tracklist keeps logging; BLT's log shows a warning,
      nothing else breaks. Restart LEDfx → next track change recolors again.
- [ ] Untagged track (no key in rekordbox) → color holds, no flicker.

## If the lights don't move

- **Nothing happens at all** — check the trigger is enabled and the deck is
  actually tempo master (the MASTER light on the CDJ).
- **Only some strips change** — expected: virtuals with no active effect are
  skipped. Anything with a live effect gets recolored.
- **Wrong color** — check the track's key tag in rekordbox. Both "8A" style
  (Camelot) and "Am"/"F#m" style are understood; anything else is ignored and
  the color holds.
- **See what it would do without touching anything**: `python3 -m keylight.cli --dry-run "<key>"`.
- BLT's own log (Help → Show Log File) carries any `keylight:` warnings.

## What's verified vs. not

Verified on this Mac mini on 2026-08-20: all 39 unit tests; the color swap
against the live LEDfx rig (7 active virtuals, only color/gradient values
change — speed, blur, background, effect type all preserved); and one real
round-trip PUT to the `end` strip, which took effect and was restored to its
original color.

Not yet verified: the BLT expression against real CDJs — that needs decks on
the network, which is the first item in the list above.
