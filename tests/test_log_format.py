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
