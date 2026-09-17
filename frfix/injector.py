"""Text injection: backspace over a wrong word and retype the correction.

There is no portable way to synthesise keystrokes on Linux, so this picks a
backend from what the session actually provides. Wayland is tried first because
on a Wayland compositor `xdotool` only reaches XWayland clients, which silently
skips most applications.
"""

import os
import shutil
import subprocess


def _wtype_available() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) and bool(shutil.which("wtype"))


def _wtype_backspaces(count: int) -> None:
    args = []
    for _ in range(count):
        args += ["-k", "BackSpace"]
    subprocess.run(["wtype", *args], timeout=5, check=False)


def _wtype_string(text: str) -> None:
    subprocess.run(["wtype", "--", text], timeout=5, check=False)


def _xdotool_available() -> bool:
    return bool(os.environ.get("DISPLAY")) and bool(shutil.which("xdotool"))


def _xdotool_release_modifiers() -> None:
    """Force-release Shift/Ctrl/Alt so injected text isn't affected."""
    subprocess.run(
        ["xdotool", "keyup", "shift", "super", "ctrl", "alt"], timeout=2, check=False
    )


def _xdotool_backspaces(count: int) -> None:
    _xdotool_release_modifiers()
    subprocess.run(["xdotool", "key", *["BackSpace"] * count], timeout=5, check=False)


def _xdotool_string(text: str) -> None:
    subprocess.run(
        ["xdotool", "type", "--delay", "0", "--", text], timeout=5, check=False
    )


_YDOTOOL_KEY_BACKSPACE = 14  # linux/input-event-codes.h KEY_BACKSPACE


def _ydotool_available() -> bool:
    if not shutil.which("ydotool"):
        return False
    probe = subprocess.run(
        ["ydotool", "key", "--help"], capture_output=True, timeout=2, check=False
    )
    return probe.returncode == 0


def _ydotool_backspaces(count: int) -> None:
    strokes = []
    for _ in range(count):
        strokes += [f"{_YDOTOOL_KEY_BACKSPACE}:1", f"{_YDOTOOL_KEY_BACKSPACE}:0"]
    subprocess.run(["ydotool", "key", *strokes], timeout=5, check=False)


def _ydotool_string(text: str) -> None:
    subprocess.run(
        ["ydotool", "type", "--key-delay", "0", "--", text], timeout=5, check=False
    )


# (name, available, send_backspaces, send_string), tried in this order because
# on a Wayland compositor xdotool only reaches XWayland clients.
BACKENDS = (
    ("wtype", _wtype_available, _wtype_backspaces, _wtype_string),
    ("xdotool", _xdotool_available, _xdotool_backspaces, _xdotool_string),
    ("ydotool", _ydotool_available, _ydotool_backspaces, _ydotool_string),
)

INSTALL_HINT = (
    "No text injection backend found. Install one of:\n"
    "  wtype    (Wayland — recommended on Hyprland/Sway/GNOME Wayland)\n"
    "  xdotool  (X11)\n"
    "  ydotool  (either, requires the ydotoold daemon running)"
)


class TextInjector:
    """Replace the last typed word with its correction."""

    def __init__(self):
        for name, available, backspaces, send_string in BACKENDS:
            try:
                if available():
                    self.backend_name = name
                    self._backspaces = backspaces
                    self._send_string = send_string
                    return
            except Exception:
                continue
        raise RuntimeError(INSTALL_HINT)

    def send_backspaces(self, count: int) -> None:
        if count <= 0:
            return
        self._backspaces(count)

    def send_string(self, text: str) -> None:
        if not text:
            return
        self._send_string(text)

    def replace_word(self, old_word: str, new_word: str) -> None:
        """Backspace over the last typed text and type its replacement."""
        self.send_backspaces(len(old_word))
        self.send_string(new_word)
