"""Characterization tests for evdev keystroke classification."""

import pytest
from evdev import ecodes

from frfix.capture import ARROW_KEYS, CHAR_KEYS, KeyAction, KeystrokeCapture

DOWN, UP, REPEAT = 1, 0, 2


class Event:
    def __init__(self, code, value):
        self.code = code
        self.value = value


@pytest.fixture
def capture():
    return KeystrokeCapture()


def press(capture, code, value=DOWN):
    return capture._process_event(Event(code, value))


@pytest.mark.parametrize(
    "code",
    [
        ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL, ecodes.KEY_LEFTALT,
        ecodes.KEY_RIGHTALT, ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
        ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA, ecodes.KEY_CAPSLOCK,
    ],
)
def test_a_modifier_on_its_own_yields_no_event(capture, code):
    assert press(capture, code) is None


def test_shift_is_reported_with_the_next_character(capture):
    press(capture, ecodes.KEY_LEFTSHIFT, DOWN)
    event = press(capture, ecodes.KEY_A)
    assert event.action is KeyAction.CHAR
    assert event.shift is True


def test_releasing_shift_clears_it(capture):
    press(capture, ecodes.KEY_LEFTSHIFT, DOWN)
    press(capture, ecodes.KEY_LEFTSHIFT, UP)
    assert press(capture, ecodes.KEY_A).shift is False


def test_right_alt_is_reported_as_altgr(capture):
    press(capture, ecodes.KEY_RIGHTALT, DOWN)
    event = press(capture, ecodes.KEY_A)
    assert event.altgr is True
    assert event.action is KeyAction.CHAR


def test_left_alt_resets_the_buffer_instead_of_typing(capture):
    press(capture, ecodes.KEY_LEFTALT, DOWN)
    assert press(capture, ecodes.KEY_A).action is KeyAction.RESET


def test_ctrl_z_is_the_undo_shortcut(capture):
    press(capture, ecodes.KEY_LEFTCTRL, DOWN)
    assert press(capture, ecodes.KEY_Z).action is KeyAction.UNDO


def test_any_other_ctrl_shortcut_resets_instead_of_typing(capture):
    press(capture, ecodes.KEY_LEFTCTRL, DOWN)
    assert press(capture, ecodes.KEY_A).action is KeyAction.RESET


def test_ctrl_z_after_releasing_ctrl_is_an_ordinary_character(capture):
    press(capture, ecodes.KEY_LEFTCTRL, DOWN)
    press(capture, ecodes.KEY_LEFTCTRL, UP)
    assert press(capture, ecodes.KEY_Z).action is KeyAction.CHAR


@pytest.mark.parametrize(
    "code, action",
    [
        (ecodes.KEY_BACKSPACE, KeyAction.BACKSPACE),
        (ecodes.KEY_SPACE, KeyAction.SPACE),
        (ecodes.KEY_ENTER, KeyAction.RESET),
        (ecodes.KEY_KPENTER, KeyAction.RESET),
        (ecodes.KEY_TAB, KeyAction.RESET),
        (ecodes.KEY_ESC, KeyAction.RESET),
        (ecodes.KEY_UP, KeyAction.RESET),
        (ecodes.KEY_HOME, KeyAction.RESET),
        (ecodes.KEY_PAGEDOWN, KeyAction.RESET),
        (ecodes.KEY_A, KeyAction.CHAR),
        (ecodes.KEY_1, KeyAction.CHAR),
        (ecodes.KEY_COMMA, KeyAction.CHAR),
    ],
)
def test_keys_are_classified(capture, code, action):
    assert press(capture, code).action is action


def test_a_character_event_carries_its_keycode(capture):
    event = press(capture, ecodes.KEY_A)
    assert event.evdev_keycode == ecodes.KEY_A


@pytest.mark.parametrize("code", [ecodes.KEY_F1, ecodes.KEY_INSERT, ecodes.KEY_MUTE])
def test_keys_that_do_not_affect_typing_are_dropped(capture, code):
    assert press(capture, code) is None


def test_key_releases_are_ignored(capture):
    assert press(capture, ecodes.KEY_A, UP) is None


def test_key_repeats_are_treated_as_typing(capture):
    assert press(capture, ecodes.KEY_A, REPEAT).action is KeyAction.CHAR


def test_the_character_table_covers_letters_digits_and_punctuation():
    assert ecodes.KEY_A in CHAR_KEYS
    assert ecodes.KEY_M in CHAR_KEYS
    assert ecodes.KEY_0 in CHAR_KEYS
    assert ecodes.KEY_SEMICOLON in CHAR_KEYS


def test_the_character_table_excludes_navigation_and_control_keys():
    assert ARROW_KEYS.isdisjoint(CHAR_KEYS)
    assert ecodes.KEY_SPACE not in CHAR_KEYS
    assert ecodes.KEY_BACKSPACE not in CHAR_KEYS
    assert ecodes.KEY_ENTER not in CHAR_KEYS
