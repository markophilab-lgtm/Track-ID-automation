import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import send_label_email as sle


def test_load_config_missing_returns_none():
    with tempfile.TemporaryDirectory() as td:
        assert sle.load_config(path=Path(td) / "nope.json") is None


def test_config_roundtrip_and_mode_600():
    import os
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sec" / "gmail_smtp.json"
        sle.save_config("me@gmail.com", "abcd efgh", path=p)
        cfg = sle.load_config(path=p)
        assert cfg == {"address": "me@gmail.com", "app_password": "abcd efgh"}
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"


def test_build_message_fields():
    msg = sle.build_message("me@gmail.com", "label@x.com", "Subj", "Body text")
    assert msg["From"] == "me@gmail.com"
    assert msg["To"] == "label@x.com"
    assert msg["Subject"] == "Subj"
    assert "Body text" in msg.get_content()


def test_build_message_rejects_multiple_recipients():
    for bad in ("a@x.com,b@y.com", "a@x.com; b@y.com"):
        try:
            sle.build_message("me@g.com", bad, "s", "b")
            assert False, "should have raised"
        except ValueError:
            pass


def test_send_uses_ssl_login_and_send_message():
    cfg = {"address": "me@gmail.com", "app_password": "pw"}
    msg = sle.build_message(cfg["address"], "label@x.com", "s", "b")
    with mock.patch.object(sle.smtplib, "SMTP_SSL") as cls:
        smtp = cls.return_value.__enter__.return_value
        sle.send(msg, cfg)
    cls.assert_called_once_with("smtp.gmail.com", 465, timeout=30)
    smtp.login.assert_called_once_with("me@gmail.com", "pw")
    smtp.send_message.assert_called_once_with(msg)


def test_main_without_config_exits_2():
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(sle, "CONFIG_PATH", Path(td) / "nope.json"):
            rc = sle.main(["--to", "a@b.com", "--subject", "s", "--body-file", "/dev/null"])
        assert rc == 2
