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

# Minor = same hue, darker. Saturation must stay 1.0: desaturating raises the
# non-dominant RGB channels, which would make minors brighter in those channels.
MINOR_SAT = 1.0
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
