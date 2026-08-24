"""Translate evdev keycodes into the characters the active layout produces.

evdev reports physical keycodes, so the layout has to be applied by hand.
This uses libxkbcommon, which is what both X11 and every Wayland compositor use
internally, so a keymap built here matches what applications actually receive.
It needs no display-server connection, which matters on Wayland: XWayland is
handed a fixed `us` keymap and never follows the compositor's layout switches,
so reading the X keysym table there returns the wrong characters.

If libxkbcommon is unavailable we fall back to a built-in French AZERTY table,
since French is the only layout frfix corrects for.

evdev keycode + 8 = xkb keycode.
"""

from . import layout as layout_mod

try:
    from xkbcommon import xkb as _xkb
except Exception:  # pragma: no cover - exercised only where libxkbcommon is absent
    _xkb = None

# Built-in fr AZERTY map, used only when libxkbcommon is unavailable.
# evdev keycode -> (base, shift, altgr). Empty string = no character.
_AZERTY: dict[int, tuple[str, str, str]] = {
    2: ("&", "1", ""),    3: ("é", "2", "~"),   4: ('"', "3", "#"),
    5: ("'", "4", "{"),   6: ("(", "5", "["),   7: ("-", "6", "|"),
    8: ("è", "7", "`"),   9: ("_", "8", "\\"),  10: ("ç", "9", "^"),
    11: ("à", "0", "@"),  12: (")", "°", "]"),  13: ("=", "+", "}"),
    16: ("a", "A", "æ"),  17: ("z", "Z", "«"),  18: ("e", "E", "€"),
    19: ("r", "R", ""),   20: ("t", "T", ""),   21: ("y", "Y", ""),
    22: ("u", "U", ""),   23: ("i", "I", ""),   24: ("o", "O", ""),
    25: ("p", "P", ""),   27: ("$", "£", "¤"),
    30: ("q", "Q", "@"),  31: ("s", "S", ""),   32: ("d", "D", ""),
    33: ("f", "F", ""),   34: ("g", "G", ""),   35: ("h", "H", ""),
    36: ("j", "J", ""),   37: ("k", "K", ""),   38: ("l", "L", ""),
    39: ("m", "M", ""),   40: ("ù", "%", ""),   41: ("²", "", ""),
    43: ("*", "µ", ""),   44: ("w", "W", ""),   45: ("x", "X", ""),
    46: ("c", "C", ""),   47: ("v", "V", ""),   48: ("b", "B", ""),
    49: ("n", "N", ""),   50: (",", "?", ""),   51: (";", ".", ""),
    52: (":", "/", ""),   53: ("!", "§", ""),
}

# Level within a layout group: 0 plain, 1 shift, 2 altgr, 3 altgr+shift.
def _level(shift: bool, altgr: bool) -> int:
    if shift and altgr:
        return 3
    if altgr:
        return 2
    if shift:
        return 1
    return 0


class KeyTranslator:
    """Map evdev keycodes to characters, and report the active layout."""

    def __init__(self, force_layout: str | None = None):
        self._backend = layout_mod.detect_backend()
        self._force_layout = force_layout
        self._keymap = None
        self._keymap_codes: list[str] = []
        self._build_keymap()

    # -- keymap ---------------------------------------------------------

    def _codes(self) -> list[str]:
        """Layout codes to compile, always with something usable in them."""
        codes = self._backend.layouts()
        if codes:
            return codes
        if self._force_layout:
            return [self._force_layout]
        return ["fr"]

    def _build_keymap(self) -> None:
        """Compile the session's layout list into an xkb keymap."""
        codes = self._codes()
        if _xkb is None:
            self._keymap_codes = codes
            return
        if self._keymap is not None and codes == self._keymap_codes:
            return
        try:
            context = _xkb.Context()
            self._keymap = context.keymap_new_from_names(
                layout=",".join(codes),
                variant=self._backend.variants(),
                options=self._backend.options(),
            )
        except Exception:
            # A bad variant/options string must not take the daemon down.
            try:
                context = _xkb.Context()
                self._keymap = context.keymap_new_from_names(layout=",".join(codes))
            except Exception:
                self._keymap = None
        self._keymap_codes = codes

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def source(self) -> str:
        return "xkbcommon" if self._keymap is not None else "builtin-azerty"

    # -- layout state ---------------------------------------------------

    def layouts(self) -> list[str]:
        return self._backend.layouts()

    def active_layout(self) -> str:
        """xkb code of the layout currently in effect, e.g. "fr"."""
        if self._force_layout:
            return self._force_layout
        codes = self._backend.layouts()
        if not codes:
            return ""
        index = self._backend.current_index()
        if index >= len(codes):
            return ""
        return codes[index]

    def is_french(self) -> bool:
        active = self.active_layout()
        return bool(active) and layout_mod.is_french_code(active)

    def switch_to(self, code: str) -> int | None:
        """Switch the session to a layout. Returns the previous index, or None."""
        codes = self._backend.layouts()
        if code not in codes:
            return None
        previous = self._backend.current_index()
        if previous < len(codes) and codes[previous] == code:
            return None
        if not self._backend.set_index(codes.index(code)):
            return None
        return previous

    def restore(self, index: int) -> None:
        self._backend.set_index(index)

    def _group(self) -> int:
        """Index of the layout to translate against."""
        codes = self._keymap_codes
        if self._force_layout:
            if self._force_layout in codes:
                return codes.index(self._force_layout)
            return 0
        index = self._backend.current_index()
        return index if index < len(codes) else 0

    # -- translation ----------------------------------------------------

    def translate(self, evdev_keycode: int, shift: bool = False,
                  altgr: bool = False) -> str | None:
        """Return the character for a keycode, or None if it is not printable."""
        self._build_keymap()
        if self._keymap is None:
            return self._translate_builtin(evdev_keycode, shift, altgr)
        return self._translate_xkb(evdev_keycode, shift, altgr)

    def _translate_builtin(self, evdev_keycode: int, shift: bool, altgr: bool) -> str | None:
        entry = _AZERTY.get(evdev_keycode)
        if not entry:
            return None
        base, shifted, alt = entry
        if altgr:
            return alt or None
        if shift:
            return shifted or None
        return base or None

    def _translate_xkb(self, evdev_keycode: int, shift: bool, altgr: bool) -> str | None:
        keycode = evdev_keycode + 8
        group = self._group()
        level = _level(shift, altgr)

        char = self._syms_to_char(keycode, group, level)
        if char is None and level != 0:
            char = self._syms_to_char(keycode, group, 0)
        return char

    def _syms_to_char(self, keycode: int, group: int, level: int) -> str | None:
        try:
            syms = self._keymap.key_get_syms_by_level(keycode, group, level)
        except Exception:
            return None
        if not syms:
            return None
        try:
            char = _xkb.keysym_to_string(syms[0])
        except Exception:
            return None
        # Dead keys and named keys (Return, BackSpace) come back as None or a
        # multi-character name; neither is a character the user typed.
        if not char or len(char) != 1:
            return None
        return char

    def close(self) -> None:
        self._keymap = None
