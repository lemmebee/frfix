"""Translate evdev keycodes into the characters the active layout produces.

evdev reports physical keycodes, so the layout has to be applied by hand.
This uses libxkbcommon, which is what both X11 and every Wayland compositor use
internally, so a keymap built here matches what applications actually receive.
It needs no display-server connection, which matters on Wayland: XWayland is
handed a fixed `us` keymap and never follows the compositor's layout switches,
so reading the X keysym table there returns the wrong characters.

libxkbcommon is a hard dependency (pyproject.toml, and setup.sh installs it on
every distro it knows), so a missing or unusable keymap is a setup problem,
not something to silently paper over with a guessed layout.

evdev keycode + 8 = xkb keycode.
"""

from . import layout as layout_mod

try:
    from xkbcommon import xkb as _xkb
except ImportError as exc:
    raise ImportError(
        "The xkbcommon Python bindings are missing. Install libxkbcommon "
        "(setup.sh does this) and reinstall frfix."
    ) from exc


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

    source = "xkbcommon"

    def __init__(self, force_layout: str | None = None):
        self._backend = layout_mod.detect_backend()
        self._force_layout = force_layout
        self._keymap = None
        self._keymap_codes: list[str] = []
        # Group last seen active, as observed by _observe(). translate() reads
        # this instead of asking the backend, so a keystroke never shells out
        # and never disagrees with what the daemon's layout check last saw.
        self._active_index = 0
        self._observe()
        if self._keymap is None:
            raise RuntimeError(
                "Could not compile an xkb keymap for the detected layout "
                f"({', '.join(self._keymap_codes)}). Try --force-layout fr."
            )

    # -- keymap ---------------------------------------------------------

    def _observe(self) -> list[str]:
        """Ask the backend for the session's layouts and active group.

        The only place the translation path reads the active group from the
        backend. Returns the session's layout codes (possibly empty).
        """
        codes = self._backend.layouts()
        self._active_index = self._backend.current_index()
        self._build_keymap(codes)
        return codes

    def _build_keymap(self, session_codes: list[str]) -> None:
        """Compile the session's layout list into an xkb keymap."""
        # Always compile something usable, even when the backend reports nothing.
        codes = session_codes or [self._force_layout or "fr"]
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

    # -- layout state ---------------------------------------------------

    def layouts(self) -> list[str]:
        return self._backend.layouts()

    def active_layout(self) -> str:
        """xkb code of the layout currently in effect, e.g. "fr"."""
        if self._force_layout:
            return self._force_layout
        codes = self._observe()
        if self._active_index >= len(codes):
            return ""
        return codes[self._active_index]

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
        self._active_index = codes.index(code)
        return previous

    def restore(self, index: int) -> None:
        self._backend.set_index(index)
        self._active_index = index

    def saw_real_key(self) -> None:
        self._backend.saw_real_key()

    def _group(self) -> int:
        """Index of the layout to translate against."""
        codes = self._keymap_codes
        if self._force_layout:
            if self._force_layout in codes:
                return codes.index(self._force_layout)
            return 0
        return self._active_index if self._active_index < len(codes) else 0

    # -- translation ----------------------------------------------------

    def translate(self, evdev_keycode: int, shift: bool = False,
                  altgr: bool = False) -> str | None:
        """Return the character for a keycode, or None if it is not printable."""
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
