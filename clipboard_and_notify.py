"""macOS clipboard + notification helpers."""

import subprocess


def copy_to_clipboard(text):
    """Pipe text to pbcopy."""
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(text.encode("utf-8"))


def notify(title, body):
    """Show a macOS notification banner via osascript."""
    title_esc = title.replace('\\', '\\\\').replace('"', '\\"')
    body_esc = body.replace('\\', '\\\\').replace('"', '\\"')
    script = f'display notification "{body_esc}" with title "{title_esc}"'
    subprocess.run(["osascript", "-e", script])
