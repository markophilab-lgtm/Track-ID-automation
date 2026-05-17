import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import clipboard_and_notify


def test_copy_to_clipboard_pipes_text():
    fake_proc = MagicMock()
    with patch.object(clipboard_and_notify.subprocess, "Popen", return_value=fake_proc) as p:
        clipboard_and_notify.copy_to_clipboard("hello world")
    p.assert_called_once_with(["pbcopy"], stdin=clipboard_and_notify.subprocess.PIPE)
    fake_proc.communicate.assert_called_once_with(b"hello world")


def test_copy_to_clipboard_unicode():
    fake_proc = MagicMock()
    with patch.object(clipboard_and_notify.subprocess, "Popen", return_value=fake_proc):
        clipboard_and_notify.copy_to_clipboard("Anthony Naples — Crystals")
    args, _ = fake_proc.communicate.call_args
    assert args[0] == "Anthony Naples — Crystals".encode("utf-8")


def test_notify_invokes_osascript():
    with patch.object(clipboard_and_notify.subprocess, "run") as r:
        clipboard_and_notify.notify("Title", "Body")
    args, kwargs = r.call_args
    cmd = args[0]
    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    assert 'display notification "Body"' in cmd[2]
    assert 'with title "Title"' in cmd[2]


def test_notify_escapes_quotes():
    with patch.object(clipboard_and_notify.subprocess, "run") as r:
        clipboard_and_notify.notify('Has "quote"', 'Body "too"')
    cmd = r.call_args[0][0]
    # Verify the quotes were escaped so osascript doesn't see them as terminators
    assert '\\"' in cmd[2]
