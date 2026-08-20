# keylight/keys.py
"""Parse rekordbox key strings (classical or Camelot) into (pitch_class, is_minor)."""

import re

# C=0 convention
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Accidental must be a literal '#' or lowercase 'b' ("AB" is not Ab major);
# only the mode suffix is case-insensitive ("M" alone still means minor).
_CLASSICAL_RE = re.compile(
    r"^([A-Ga-g])\s*([#b]?)\s*((?i:m|min|minor|maj|major))?$")
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
