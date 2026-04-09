"""Translate evdev keycodes to actual characters using X11 keysym tables.

evdev gives physical keycodes. We use python-xlib to look up the correct
character based on the active keyboard group (layout) and modifier state.

evdev keycode + 8 = X11 keycode.
keysym index = (group * 4) + level, where level depends on shift/altgr.
"""

import subprocess

from Xlib import display, XK


class KeyTranslator:
    """Translate evdev keycodes to characters using X11 keysym tables."""

    def __init__(self, force_layout: str | None = None):
        self._display = display.Display()
        self._group = 0  # Active keyboard group (0-based)
        self._layouts: list[str] = []
        self._force_layout = force_layout
        self._refresh_layout_info()
        # If forced, set group to that layout
        if self._force_layout and self._force_layout in self._layouts:
            self._group = self._layouts.index(self._force_layout)
        elif self._force_layout:
            # Layout not in list, try xmodmap/setxkbmap fallback
            self._refresh_layout_from_xkb()

    def _refresh_layout_info(self) -> None:
        """Get layout list and active group from gsettings."""
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                capture_output=True, text=True, timeout=1,
            )
            self._layouts = []
            for part in result.stdout.strip().split("'"):
                if len(part) <= 5 and part.isalpha() and part != "xkb":
                    self._layouts.append(part)
        except Exception:
            self._layouts = []

        self._update_group()

    def _refresh_layout_from_xkb(self) -> None:
        """Fallback: get layout list from setxkbmap."""
        try:
            result = subprocess.run(
                ["setxkbmap", "-query"],
                capture_output=True, text=True, timeout=1,
            )
            for line in result.stdout.splitlines():
                if line.strip().startswith("layout:"):
                    layouts_str = line.split(":", 1)[1].strip()
                    self._layouts = [l.strip() for l in layouts_str.split(",")]
                    if self._force_layout and self._force_layout in self._layouts:
                        self._group = self._layouts.index(self._force_layout)
                    break
        except Exception:
            pass

    def _update_group(self) -> None:
        """Update the active group index."""
        if self._force_layout:
            # Don't change group if forced
            return
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.input-sources", "current"],
                capture_output=True, text=True, timeout=1,
            )
            self._group = int(result.stdout.strip().split()[-1])
        except Exception:
            self._group = 0

    def update_group(self) -> None:
        """Public method to refresh active group."""
        self._update_group()

    def get_active_layout(self) -> str:
        """Return the name of the active layout."""
        self._update_group()
        if self._group < len(self._layouts):
            return self._layouts[self._group]
        return ""

    def is_french(self) -> bool:
        """Check if current layout is French."""
        return self.get_active_layout() == "fr"

    def translate(self, evdev_keycode: int, shift: bool = False,
                  altgr: bool = False) -> str | None:
        """Translate an evdev keycode to a character string.

        Args:
            evdev_keycode: The evdev keycode (e.g., KEY_A = 30)
            shift: Whether Shift is held
            altgr: Whether AltGr is held

        Returns:
            The character string, or None if not a printable character.
        """
        x11_keycode = evdev_keycode + 8

        # Compute keysym index: group * 4 + level
        # level 0 = plain, 1 = shift, 2 = altgr, 3 = altgr+shift
        level = 0
        if shift:
            level = 1
        if altgr:
            level = 2
        if shift and altgr:
            level = 3

        keysym_index = (self._group * 4) + level
        keysym = self._display.keycode_to_keysym(x11_keycode, keysym_index)

        if keysym == 0:
            # Try without altgr/shift variants
            keysym = self._display.keycode_to_keysym(x11_keycode, self._group * 4)

        if keysym == 0:
            return None

        # Convert keysym to string
        char = XK.keysym_to_string(keysym)
        if char and len(char) == 1:
            return char

        # Try Unicode keysym range (0x01000000 + codepoint)
        if 0x01000000 <= keysym <= 0x0110FFFF:
            return chr(keysym - 0x01000000)

        # Try direct Unicode mapping for common French chars
        if 0x00c0 <= keysym <= 0x00ff:
            return chr(keysym)

        return None

    def close(self) -> None:
        """Clean up."""
        try:
            self._display.close()
        except Exception:
            pass
