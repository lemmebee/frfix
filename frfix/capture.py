"""System-wide keystroke capture using evdev."""

import asyncio
from dataclasses import dataclass
from enum import Enum, auto

import evdev
from evdev import InputDevice, ecodes


class KeyAction(Enum):
    CHAR = auto()
    BACKSPACE = auto()
    SPACE = auto()
    UNDO = auto()          # Ctrl+Z
    RESET = auto()         # Enter/Tab/Escape/arrows/other shortcuts: drop the buffer


@dataclass
class KeyEvent:
    action: KeyAction
    evdev_keycode: int = 0
    shift: bool = False
    altgr: bool = False


# Mapping from evdev keycodes to characters (base, shifted)
# French AZERTY layout handled by X11 — evdev gives physical keycodes,
# but we rely on X11 for the actual character. We use evdev only to detect
# key categories (letter vs backspace vs arrow etc.)
CHAR_KEYS = set(range(ecodes.KEY_Q, ecodes.KEY_P + 1)) | \
            set(range(ecodes.KEY_A, ecodes.KEY_L + 1)) | \
            set(range(ecodes.KEY_Z, ecodes.KEY_M + 1)) | \
            {ecodes.KEY_MINUS, ecodes.KEY_EQUAL, ecodes.KEY_LEFTBRACE,
             ecodes.KEY_RIGHTBRACE, ecodes.KEY_SEMICOLON, ecodes.KEY_APOSTROPHE,
             ecodes.KEY_GRAVE, ecodes.KEY_BACKSLASH, ecodes.KEY_COMMA,
             ecodes.KEY_DOT, ecodes.KEY_SLASH,
             ecodes.KEY_0, ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_3,
             ecodes.KEY_4, ecodes.KEY_5, ecodes.KEY_6, ecodes.KEY_7,
             ecodes.KEY_8, ecodes.KEY_9}

ARROW_KEYS = {ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFT, ecodes.KEY_RIGHT,
              ecodes.KEY_HOME, ecodes.KEY_END, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN}


class KeystrokeCapture:
    """Monitor keyboard events via evdev (read-only, no grab)."""

    def __init__(self):
        self._devices: list[InputDevice] = []
        self._ctrl_held = False
        self._alt_held = False
        self._shift_held = False
        self._altgr_held = False  # Right Alt on AZERTY = AltGr

    def _find_keyboards(self) -> list[InputDevice]:
        """Find keyboard input devices."""
        keyboards = []
        for path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(path)
                caps = dev.capabilities(verbose=False)
                # Check if device has EV_KEY with letter keys
                if ecodes.EV_KEY in caps:
                    key_caps = caps[ecodes.EV_KEY]
                    if ecodes.KEY_A in key_caps and ecodes.KEY_Z in key_caps:
                        keyboards.append(dev)
            except (PermissionError, OSError):
                continue
        return keyboards

    async def events(self):
        """Async generator yielding KeyEvent objects."""
        self._devices = self._find_keyboards()
        if not self._devices:
            raise RuntimeError(
                "No keyboard devices found. Make sure you're in the 'input' group: "
                "sudo usermod -aG input $USER (then log out and back in)"
            )

        # Create async tasks for each keyboard
        self._queue: asyncio.Queue[KeyEvent] = asyncio.Queue()

        async def read_device(device: InputDevice):
            try:
                async for event in device.async_read_loop():
                    if event.type != ecodes.EV_KEY:
                        continue
                    key_event = self._process_event(event)
                    if key_event:
                        await self._queue.put(key_event)
            except OSError:
                pass  # Device disconnected

        tasks = [asyncio.create_task(read_device(d)) for d in self._devices]

        try:
            while True:
                event = await self._queue.get()
                yield event
        finally:
            for t in tasks:
                t.cancel()

    def _process_event(self, event) -> KeyEvent | None:
        """Convert evdev event to KeyEvent."""
        key = event.code
        # 1 = key down, 0 = key up, 2 = key repeat
        is_down = event.value in (1, 2)

        # Track modifier state
        if key in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
            self._ctrl_held = is_down
            return None
        if key == ecodes.KEY_LEFTALT:
            self._alt_held = is_down
            return None
        if key == ecodes.KEY_RIGHTALT:
            # Right Alt = AltGr on AZERTY
            self._altgr_held = is_down
            return None
        if key in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            self._shift_held = is_down
            return None
        if key in (ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA, ecodes.KEY_CAPSLOCK):
            return None

        # Only process key down and repeat
        if not is_down:
            return None

        # Ctrl+Z = undo
        if self._ctrl_held and key == ecodes.KEY_Z:
            return KeyEvent(action=KeyAction.UNDO)

        # Skip if ctrl or alt held (shortcuts, not typing)
        if self._ctrl_held or self._alt_held:
            return KeyEvent(action=KeyAction.RESET)

        if key == ecodes.KEY_BACKSPACE:
            return KeyEvent(action=KeyAction.BACKSPACE)
        if key == ecodes.KEY_SPACE:
            return KeyEvent(action=KeyAction.SPACE)
        if key in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER, ecodes.KEY_TAB, ecodes.KEY_ESC):
            return KeyEvent(action=KeyAction.RESET)
        if key in ARROW_KEYS:
            return KeyEvent(action=KeyAction.RESET)
        if key in CHAR_KEYS:
            return KeyEvent(action=KeyAction.CHAR, evdev_keycode=key,
                            shift=self._shift_held, altgr=self._altgr_held)

        return None
