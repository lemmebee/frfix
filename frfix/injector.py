"""Text injection: backspace over a wrong word and retype the correction.

There is no portable way to synthesise keystrokes on Linux, so this picks a
backend from what the session actually provides. Wayland is tried first because
on a Wayland compositor `xdotool` only reaches XWayland clients, which silently
skips most applications.
"""

import os
import shutil
import subprocess


class InjectorBackend:
    """Interface: send raw backspaces and typed text to the focused window."""

    name = "none"

    @staticmethod
    def available() -> bool:
        return False

    def send_backspaces(self, count: int) -> None:
        raise NotImplementedError

    def send_string(self, text: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class WtypeBackend(InjectorBackend):
    """Wayland virtual-keyboard protocol. Reaches every client, X or native."""

    name = "wtype"

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("WAYLAND_DISPLAY")) and bool(shutil.which("wtype"))

    def send_backspaces(self, count: int) -> None:
        args = []
        for _ in range(count):
            args += ["-k", "BackSpace"]
        subprocess.run(["wtype", *args], timeout=5, check=False)

    def send_string(self, text: str) -> None:
        subprocess.run(["wtype", "--", text], timeout=5, check=False)


class XdotoolBackend(InjectorBackend):
    """X11 / XWayland via XTEST."""

    name = "xdotool"

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("DISPLAY")) and bool(shutil.which("xdotool"))

    def _release_modifiers(self) -> None:
        """Force-release Shift/Ctrl/Alt so injected text isn't affected."""
        subprocess.run(
            ["xdotool", "keyup", "shift", "super", "ctrl", "alt"],
            timeout=2, check=False,
        )

    def send_backspaces(self, count: int) -> None:
        self._release_modifiers()
        subprocess.run(
            ["xdotool", "key", *["BackSpace"] * count], timeout=5, check=False
        )

    def send_string(self, text: str) -> None:
        subprocess.run(
            ["xdotool", "type", "--delay", "0", "--", text], timeout=5, check=False
        )


class YdotoolBackend(InjectorBackend):
    """uinput-based, display-server independent. Needs the ydotoold daemon."""

    name = "ydotool"

    KEY_BACKSPACE = 14  # linux/input-event-codes.h KEY_BACKSPACE

    @staticmethod
    def available() -> bool:
        if not shutil.which("ydotool"):
            return False
        probe = subprocess.run(
            ["ydotool", "key", "--help"], capture_output=True, timeout=2, check=False
        )
        return probe.returncode == 0

    def send_backspaces(self, count: int) -> None:
        strokes = []
        for _ in range(count):
            strokes += [f"{self.KEY_BACKSPACE}:1", f"{self.KEY_BACKSPACE}:0"]
        subprocess.run(["ydotool", "key", *strokes], timeout=5, check=False)

    def send_string(self, text: str) -> None:
        subprocess.run(
            ["ydotool", "type", "--key-delay", "0", "--", text], timeout=5, check=False
        )


BACKENDS = (WtypeBackend, XdotoolBackend, YdotoolBackend)

INSTALL_HINT = (
    "No text injection backend found. Install one of:\n"
    "  wtype    (Wayland — recommended on Hyprland/Sway/GNOME Wayland)\n"
    "  xdotool  (X11)\n"
    "  ydotool  (either, requires the ydotoold daemon running)"
)


def detect_backend() -> InjectorBackend:
    """Return the first injection backend usable in this session."""
    for backend_cls in BACKENDS:
        try:
            if backend_cls.available():
                return backend_cls()
        except Exception:
            continue
    raise RuntimeError(INSTALL_HINT)


class TextInjector:
    """Replace the last typed word with its correction."""

    def __init__(self, backend: InjectorBackend | None = None):
        self._backend = backend or detect_backend()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def send_backspaces(self, count: int) -> None:
        if count <= 0:
            return
        self._backend.send_backspaces(count)

    def send_string(self, text: str) -> None:
        if not text:
            return
        self._backend.send_string(text)

    def replace_word(self, old_word: str, new_word: str, extra_backspaces: int = 0) -> None:
        """Replace the last typed word, restoring any separator that followed it."""
        self.send_backspaces(len(old_word) + extra_backspaces)
        self.send_string(new_word)
        if extra_backspaces > 0:
            self.send_string(" ")

    def close(self) -> None:
        self._backend.close()
