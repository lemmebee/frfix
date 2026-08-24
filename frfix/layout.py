"""Keyboard layout detection and switching.

frfix only corrects while a French layout is active. Every desktop exposes
that fact differently, so this module probes a chain of backends and uses the
first one that answers. Nothing here is distro-specific: the backends key off
the compositor / desktop actually running, and fall back to xkb defaults.
"""

import json
import os
import shutil
import subprocess
from functools import lru_cache

XKB_RULES_LST = "/usr/share/X11/xkb/rules/base.lst"

# Layouts whose xkb code counts as "French".
FRENCH_CODES = {"fr", "ca(fr)", "be", "ch(fr)"}


def _run(cmd: list[str], timeout: float = 1.0,
         env: dict[str, str] | None = None) -> str | None:
    """Run a command, return stdout or None if it failed or is missing."""
    if not shutil.which(cmd[0]):
        return None
    child_env = None
    if env:
        child_env = {**os.environ, **env}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            check=False, env=child_env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _runtime_dir() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def hyprland_signature() -> str | None:
    """Find Hyprland's instance signature.

    A systemd user service does not inherit HYPRLAND_INSTANCE_SIGNATURE, and
    hyprctl refuses to run without it, so fall back to discovering the live
    instance from the runtime directory.
    """
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if signature:
        return signature
    hypr_dir = os.path.join(_runtime_dir(), "hypr")
    try:
        entries = [
            entry for entry in os.scandir(hypr_dir)
            if entry.is_dir() and os.path.exists(os.path.join(entry.path, ".socket.sock"))
        ]
    except OSError:
        return None
    if not entries:
        return None
    newest = max(entries, key=lambda entry: entry.stat().st_mtime)
    return newest.name


def sway_socket() -> str | None:
    """Find Sway's IPC socket, which a user service also does not inherit."""
    sock = os.environ.get("SWAYSOCK")
    if sock and os.path.exists(sock):
        return sock
    try:
        candidates = [
            entry.path for entry in os.scandir(_runtime_dir())
            if entry.name.startswith("sway-ipc.") and entry.name.endswith(".sock")
        ]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


@lru_cache(maxsize=1)
def _xkb_descriptions() -> dict[str, str]:
    """Map xkb layout code -> human description, e.g. {"fr": "French"}.

    Read from xkeyboard-config's rules list, which ships on every distro that
    has X11 or Wayland keyboard support. Compositors report the description
    (Hyprland's `active_keymap`, Sway's `xkb_active_layout_name`), so this is
    what lets us turn a display name back into a code.
    """
    table: dict[str, str] = {}
    try:
        with open(XKB_RULES_LST, encoding="utf-8", errors="replace") as fh:
            in_section = False
            for line in fh:
                if line.startswith("! layout"):
                    in_section = True
                    continue
                if line.startswith("!"):
                    in_section = False
                    continue
                if not in_section:
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    table[parts[0]] = parts[1].strip()
    except OSError:
        pass
    return table


def _code_for_description(description: str) -> str | None:
    """Reverse-lookup an xkb code from a compositor's display name."""
    if not description:
        return None
    for code, desc in _xkb_descriptions().items():
        if desc == description:
            return code
    # Compositors sometimes append a variant, e.g. "French (AZERTY)".
    head = description.split(" (")[0]
    for code, desc in _xkb_descriptions().items():
        if desc == head or desc.split(" (")[0] == head:
            return code
    return None


class LayoutBackend:
    """Interface: report the configured layouts and which one is active."""

    name = "none"

    def available(self) -> bool:
        return False

    def layouts(self) -> list[str]:
        """Configured layout codes, in switch order."""
        return []

    def current_index(self) -> int:
        """Index into layouts() of the active layout."""
        return 0

    def set_index(self, index: int) -> bool:
        """Switch to a layout. Return True if the switch was applied."""
        return False

    def variants(self) -> str:
        """Comma-separated xkb variants, parallel to layouts(). May be empty."""
        return ""

    def options(self) -> str:
        """Comma-separated xkb options, e.g. "grp:alt_shift_toggle"."""
        return ""


class HyprlandBackend(LayoutBackend):
    """Hyprland: `hyprctl devices` reports layouts and the active keymap."""

    name = "hyprland"

    def __init__(self):
        self._device: str | None = None
        self._signature = hyprland_signature()

    def available(self) -> bool:
        return bool(self._signature) and bool(shutil.which("hyprctl"))

    def _hyprctl(self, args: list[str], timeout: float = 1.0) -> str | None:
        return _run(
            ["hyprctl", *args], timeout,
            env={"HYPRLAND_INSTANCE_SIGNATURE": self._signature or ""},
        )

    def _main_keyboard(self) -> dict | None:
        out = self._hyprctl(["devices", "-j"])
        if not out:
            return None
        try:
            keyboards = json.loads(out).get("keyboards", [])
        except (json.JSONDecodeError, AttributeError):
            return None
        if not keyboards:
            return None
        for kb in keyboards:
            if kb.get("main"):
                self._device = kb.get("name")
                return kb
        self._device = keyboards[0].get("name")
        return keyboards[0]

    def layouts(self) -> list[str]:
        kb = self._main_keyboard()
        if not kb:
            return []
        return [part.strip() for part in kb.get("layout", "").split(",") if part.strip()]

    def current_index(self) -> int:
        kb = self._main_keyboard()
        if not kb:
            return 0
        code = _code_for_description(kb.get("active_keymap", ""))
        configured = [p.strip() for p in kb.get("layout", "").split(",") if p.strip()]
        if code and code in configured:
            return configured.index(code)
        return 0

    def set_index(self, index: int) -> bool:
        if self._device is None:
            self._main_keyboard()
        if self._device is None:
            return False
        return self._hyprctl(["switchxkblayout", self._device, str(index)], 2.0) is not None

    def _getoption(self, name: str) -> str:
        out = self._hyprctl(["getoption", f"input:{name}", "-j"])
        if not out:
            return ""
        try:
            value = json.loads(out).get("str", "")
        except json.JSONDecodeError:
            return ""
        # Hyprland spells an unset string option "[[EMPTY]]".
        return "" if value == "[[EMPTY]]" else value

    def variants(self) -> str:
        return self._getoption("kb_variant")

    def options(self) -> str:
        return self._getoption("kb_options")


class SwayBackend(LayoutBackend):
    """Sway / i3-on-Wayland: `swaymsg -t get_inputs` carries layout state."""

    name = "sway"

    def __init__(self):
        self._socket = sway_socket()

    def available(self) -> bool:
        return bool(self._socket) and bool(shutil.which("swaymsg"))

    def _swaymsg(self, args: list[str], timeout: float = 1.0) -> str | None:
        return _run(["swaymsg", *args], timeout, env={"SWAYSOCK": self._socket or ""})

    def _keyboard(self) -> dict | None:
        out = self._swaymsg(["-t", "get_inputs", "-r"])
        if not out:
            return None
        try:
            inputs = json.loads(out)
        except json.JSONDecodeError:
            return None
        for dev in inputs:
            if dev.get("type") == "keyboard" and dev.get("xkb_layout_names"):
                return dev
        return None

    def layouts(self) -> list[str]:
        kb = self._keyboard()
        if not kb:
            return []
        codes = []
        for display_name in kb.get("xkb_layout_names", []):
            codes.append(_code_for_description(display_name) or display_name)
        return codes

    def current_index(self) -> int:
        kb = self._keyboard()
        if not kb:
            return 0
        return int(kb.get("xkb_active_layout_index", 0))

    def set_index(self, index: int) -> bool:
        return self._swaymsg(
            ["input", "type:keyboard", "xkb_switch_layout", str(index)], 2.0
        ) is not None


class GnomeBackend(LayoutBackend):
    """GNOME: layouts live in the org.gnome.desktop.input-sources schema."""

    name = "gnome"

    def available(self) -> bool:
        if not shutil.which("gsettings"):
            return False
        return bool(self.layouts())

    def layouts(self) -> list[str]:
        out = _run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"])
        if not out:
            return []
        codes = []
        for part in out.strip().split("'"):
            if part and part != "xkb" and len(part) <= 8 and part.replace("+", "").isalnum():
                codes.append(part)
        return codes

    def current_index(self) -> int:
        out = _run(["gsettings", "get", "org.gnome.desktop.input-sources", "current"])
        if not out:
            return 0
        try:
            return int(out.strip().split()[-1])
        except (ValueError, IndexError):
            return 0

    def set_index(self, index: int) -> bool:
        return _run(
            ["gsettings", "set", "org.gnome.desktop.input-sources",
             "current", f"uint32 {index}"], 2.0
        ) is not None


class XkbBackend(LayoutBackend):
    """Plain X11: layouts from setxkbmap, active group from the XKB extension."""

    name = "xkb"

    def available(self) -> bool:
        return bool(os.environ.get("DISPLAY")) and bool(self.layouts())

    def layouts(self) -> list[str]:
        value = self._query("layout")
        return [part.strip() for part in value.split(",") if part.strip()]

    def _query(self, field: str) -> str:
        out = _run(["setxkbmap", "-query"])
        if not out:
            return ""
        for line in out.splitlines():
            if line.strip().startswith(f"{field}:"):
                return line.split(":", 1)[1].strip()
        return ""

    def variants(self) -> str:
        return self._query("variant")

    def options(self) -> str:
        return self._query("options")

    def current_index(self) -> int:
        # python-xlib ships no XKB extension, so the active group has to come
        # from a helper. Without one we assume the first layout.
        out = _run(["xkblayout-state", "print", "%c"])
        if out:
            try:
                return int(out.strip())
            except ValueError:
                pass
        return 0

    def set_index(self, index: int) -> bool:
        codes = self.layouts()
        if index >= len(codes):
            return False
        return _run(["setxkbmap", codes[index]], 2.0) is not None


class EnvBackend(LayoutBackend):
    """Last resort: honour XKB_DEFAULT_LAYOUT (set by most Wayland sessions)."""

    name = "env"

    def available(self) -> bool:
        return bool(os.environ.get("XKB_DEFAULT_LAYOUT"))

    def layouts(self) -> list[str]:
        value = os.environ.get("XKB_DEFAULT_LAYOUT", "")
        return [part.strip() for part in value.split(",") if part.strip()]

    def variants(self) -> str:
        return os.environ.get("XKB_DEFAULT_VARIANT", "")

    def options(self) -> str:
        return os.environ.get("XKB_DEFAULT_OPTIONS", "")


BACKENDS = (HyprlandBackend, SwayBackend, GnomeBackend, XkbBackend, EnvBackend)


def detect_backend() -> LayoutBackend:
    """Return the first backend that can answer for the running session."""
    for backend_cls in BACKENDS:
        backend = backend_cls()
        try:
            if backend.available():
                return backend
        except Exception:
            continue
    return LayoutBackend()


def is_french_code(code: str) -> bool:
    """Return True if an xkb layout code is a French layout."""
    return code.split(":")[0] in FRENCH_CODES


def is_french_layout() -> bool:
    """Return True if the active keyboard layout is French."""
    backend = detect_backend()
    codes = backend.layouts()
    if not codes:
        return False
    index = backend.current_index()
    if index >= len(codes):
        return False
    return is_french_code(codes[index])
