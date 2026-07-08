#!/bin/bash
# Upload to SoundCloud — double-click uploader for WTHS Radio sets.
# Wraps soundcloud_publish.py / post_tracklist.py in ~/Desktop/TRACK ID PROJECT.

PROJECT="$HOME/Desktop/TRACK ID PROJECT"
OUTDIR="$HOME/Desktop/deploy_output"
MOVIES="$HOME/Movies"

finish() {
  echo ""
  read -r -p "Press Enter to close this window..."
  exit "${1:-0}"
}

echo "=========================================="
echo "  Upload to SoundCloud — WTHS Radio"
echo "=========================================="
echo ""

# --- 1. Pick the recording -----------------------------------------------
NEWEST=$(ls -t "$MOVIES"/*.mov 2>/dev/null | head -1)
if [ -z "$NEWEST" ]; then
  echo "No recordings (.mov files) found in your Movies folder."
  echo "Record the stream first, then double-click this again."
  finish 1
fi

MOVIE="$NEWEST"
SIZE=$(du -h "$MOVIE" | cut -f1 | tr -d ' ')
echo "Newest recording: $(basename "$MOVIE")  ($SIZE)"
read -r -p "Use this one? (y/n) " USE_NEWEST

if [[ ! "$USE_NEWEST" =~ ^[Yy] ]]; then
  echo ""
  echo "Recent recordings:"
  i=0
  CHOICES=()
  while IFS= read -r f; do
    i=$((i+1))
    CHOICES+=("$f")
    echo "  $i) $(basename "$f")  ($(du -h "$f" | cut -f1 | tr -d ' '))"
    [ "$i" -ge 9 ] && break
  done < <(ls -t "$MOVIES"/*.mov 2>/dev/null)
  echo ""
  read -r -p "Type the number of the one you want: " PICK
  if [[ "$PICK" =~ ^[1-9]$ ]] && [ "$PICK" -le "${#CHOICES[@]}" ]; then
    MOVIE="${CHOICES[$((PICK-1))]}"
  else
    echo "That wasn't a valid number. Nothing uploaded."
    finish 1
  fi
fi
echo ""
echo "Using: $(basename "$MOVIE")"
echo ""

# --- 2. Artist name -------------------------------------------------------
ARTIST=""
while [ -z "$ARTIST" ]; do
  read -r -p "Artist name? " ARTIST
done

# --- 3. Date + title (D.M.Y, no leading zeros, no parentheses) ------------
BASENAME=$(basename "$MOVIE")
if [[ "$BASENAME" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
  YEAR="${BASH_REMATCH[1]}"; MONTH="${BASH_REMATCH[2]}"; DAY="${BASH_REMATCH[3]}"
else
  # Filename has no date — use the file's modification date instead.
  YEAR=$(stat -f %Sm -t %Y "$MOVIE"); MONTH=$(stat -f %Sm -t %m "$MOVIE"); DAY=$(stat -f %Sm -t %d "$MOVIE")
fi
TITLE="$ARTIST @ WTHS Radio $((10#$DAY)).$((10#$MONTH)).$YEAR"
ISODATE="$YEAR-$MONTH-$DAY"

# --- 4. Description: tracklist or simple ----------------------------------
mkdir -p "$OUTDIR"
DESC="$OUTDIR/soundcloud_description.txt"

read -r -p "Include the tracklist? (y for a normal set / n for own productions) " WANT_TRACKLIST
echo ""

write_simple_description() {
  cat > "$DESC" <<EOF
A live set of original productions by $ARTIST.

Recorded live $ISODATE.
Promotional use only — not monetized.
EOF
  echo "Using a simple description (no tracklist)."
}

if [[ "$WANT_TRACKLIST" =~ ^[Yy] ]]; then
  echo "Building the tracklist (this can take a few minutes)..."
  if python3 "$PROJECT/post_tracklist.py" --skip-mixcloud --skip-youtube \
       --artist "$ARTIST" --movie "$MOVIE" --write-descriptions "$OUTDIR"; then
    echo "Tracklist ready."
  else
    echo ""
    echo "The tracklist build failed (see the messages above)."
    read -r -p "Continue with a simple description instead? (y/n) " FALLBACK
    if [[ "$FALLBACK" =~ ^[Yy] ]]; then
      write_simple_description
    else
      echo "Nothing uploaded."
      finish 1
    fi
  fi
else
  write_simple_description
fi
echo ""

# --- 5. Preview ------------------------------------------------------------
echo "------------------------------------------"
echo "  PREVIEW"
echo "------------------------------------------"
if ! python3 "$PROJECT/soundcloud_publish.py" --dry-run \
     --movie "$MOVIE" --title "$TITLE" --description-file "$DESC"; then
  echo ""
  echo "Couldn't build the preview (see the messages above). Nothing uploaded."
  finish 1
fi
echo ""
read -r -p "Upload this to SoundCloud? (y/n) " GO
if [[ ! "$GO" =~ ^[Yy] ]]; then
  echo "OK — nothing uploaded."
  finish 0
fi

# --- 6. Upload (with one retry if the SoundCloud login expired) ------------
echo ""
echo "Uploading — this takes a few minutes. Leave this window open."
python3 "$PROJECT/soundcloud_publish.py" \
  --movie "$MOVIE" --title "$TITLE" --description-file "$DESC"
CODE=$?

if [ "$CODE" -eq 4 ]; then
  echo ""
  echo "Your SoundCloud login has expired. Reconnecting — your browser will open;"
  echo "log in to SoundCloud and approve, then come back here."
  if python3 "$PROJECT/soundcloud_publish.py" --setup; then
    echo ""
    echo "Reconnected. Uploading again..."
    python3 "$PROJECT/soundcloud_publish.py" \
      --movie "$MOVIE" --title "$TITLE" --description-file "$DESC"
    CODE=$?
  fi
fi

echo ""
if [ "$CODE" -eq 0 ]; then
  echo "Done! The SoundCloud link is printed above (line starting with \"Uploaded:\")."
else
  echo "The upload didn't finish (see the messages above)."
  echo "You can just double-click this file to try again."
fi
finish "$CODE"
