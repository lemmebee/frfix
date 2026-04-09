"""Text injection via xdotool — backspaces + retypes corrected text."""

import subprocess

from Xlib import display


class TextInjector:
    """Inject keystrokes via xdotool."""

    def __init__(self):
        self._display = display.Display()
        self._root = self._display.screen().root

    def _release_modifiers(self) -> None:
        """Force-release Shift/Ctrl/Alt so injected text isn't affected."""
        subprocess.run(
            ["xdotool", "keyup", "shift", "super", "ctrl", "alt"],
            timeout=2,
        )

    def send_backspaces(self, count: int) -> None:
        """Send N backspace key presses."""
        if count <= 0:
            return
        self._release_modifiers()
        subprocess.run(
            ["xdotool", "key", *["BackSpace"] * count],
            timeout=2,
        )

    def send_string(self, text: str) -> None:
        """Type a string."""
        if not text:
            return
        subprocess.run(
            ["xdotool", "type", "--delay", "0", text],
            timeout=2,
        )

    def replace_word(self, old_word: str, new_word: str, extra_backspaces: int = 0) -> None:
        """Replace the last typed word."""
        total_backspaces = len(old_word) + extra_backspaces
        self.send_backspaces(total_backspaces)
        self.send_string(new_word)
        if extra_backspaces > 0:
            self.send_string(" ")

    def get_cursor_position(self) -> tuple[int, int]:
        """Get current mouse cursor position."""
        pointer = self._root.query_pointer()
        return pointer.root_x, pointer.root_y

    def close(self) -> None:
        """Clean up."""
        self._display.close()
