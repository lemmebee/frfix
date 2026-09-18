"""End-to-end tests for the daemon's correction pipeline."""

import asyncio
import contextlib
import json

import pytest
from test_xchar import FakeBackend

from frfix import layout as layout_mod
from frfix.capture import KeyAction, KeyEvent
from frfix.daemon import FrfixDaemon
from frfix.layout import HyprlandBackend


class FakeInjector:
    backend_name = "fake"

    def __init__(self):
        self.calls = []

    def send_backspaces(self, count):
        self.calls.append(("bs", count))

    def send_string(self, text):
        self.calls.append(("type", text))

    def replace_word(self, old_word, new_word):
        self.calls.append(("replace", old_word, new_word))


class FakeCorrector:
    def __init__(self, words=None, sentence_corrections=None):
        self.words = words or {}
        self.sentence_corrections = sentence_corrections or []
        self.checked = []
        self.sentences = []

    def check_word(self, word):
        self.checked.append(word)
        return self.words.get(word)

    def check_sentence(self, sentence):
        self.sentences.append(sentence)
        return list(self.sentence_corrections)


class FakeCapture:
    """Replays a fixed list of key events, then stops."""

    def __init__(self, events):
        self._events = list(events)

    async def events(self):
        for event in self._events:
            yield event


class FakeTranslator:
    backend_name = "fake"
    source = "fake"

    def __init__(self):
        self.french = True

    def translate(self, keycode, shift=False, altgr=False):
        return chr(keycode) if keycode else None

    def layouts(self):
        return ["fr"]

    def active_layout(self):
        return "fr"

    def is_french(self):
        return self.french

    def switch_to(self, code):
        return None

    def restore(self, index):
        pass

    def saw_real_key(self):
        pass

    def close(self):
        pass


@pytest.fixture
def daemon(monkeypatch):
    monkeypatch.setattr("frfix.daemon.load_config", lambda: _config())
    monkeypatch.setattr("frfix.daemon.TextInjector", lambda: FakeInjector())
    monkeypatch.setattr("frfix.daemon.KeystrokeCapture", lambda: object())
    monkeypatch.setattr(
        "frfix.daemon.KeyTranslator", lambda force_layout=None: FakeTranslator()
    )
    monkeypatch.setattr(
        "frfix.daemon.FrenchCorrector",
        lambda user_words=None: FakeCorrector({"ca": "ça", "cest": "c'est"}),
    )
    instance = FrfixDaemon(skip_layout_check=True)
    instance._is_french = True
    return instance


def _config():
    class Cfg:
        spelling = True
        grammar = True
        auto_switch_layout = False
        user_words = set()

    return Cfg()


def send(daemon, event):
    asyncio.run(daemon._handle_key(event))


def type_text(daemon, text):
    for char in text:
        if char == " ":
            send(daemon, KeyEvent(action=KeyAction.SPACE))
        else:
            send(daemon, KeyEvent(action=KeyAction.CHAR, evdev_keycode=ord(char)))


def test_a_wrong_word_is_replaced_when_the_space_is_typed(daemon):
    type_text(daemon, "ca ")
    assert daemon.injector.calls == [("replace", "ca ", "ça ")]


def test_nothing_is_injected_while_the_word_is_still_being_typed(daemon):
    type_text(daemon, "ca")
    assert daemon.injector.calls == []


def test_a_correct_word_is_left_alone(daemon):
    type_text(daemon, "bonjour ")
    assert daemon.injector.calls == []


def test_each_word_is_corrected_independently(daemon):
    type_text(daemon, "ca cest ")
    assert daemon.injector.calls == [
        ("replace", "ca ", "ça "),
        ("replace", "cest ", "c'est "),
    ]


def test_punctuation_also_completes_a_word_and_is_restored(daemon):
    type_text(daemon, "ca,")
    assert daemon.injector.calls == [("replace", "ca,", "ça,")]


def test_spelling_can_be_turned_off(daemon):
    daemon.config.spelling = False
    type_text(daemon, "ca ")
    assert daemon.injector.calls == []


def test_a_correction_identical_to_the_typed_word_is_not_injected(daemon):
    daemon.corrector.words = {"ca": "ca"}
    type_text(daemon, "ca ")
    assert daemon.injector.calls == []


def test_a_sentence_ending_corrects_the_final_word_and_restores_the_period(daemon):
    type_text(daemon, "ca.")
    assert daemon.injector.calls == [("replace", "ca.", "ça.")]


def test_the_grammar_check_sees_the_sentence_as_corrected_on_screen(daemon):
    type_text(daemon, "ca va bien.")
    assert daemon.corrector.sentences == ["ça va bien."]


def test_the_grammar_check_sees_a_final_word_corrected_at_the_period(daemon):
    type_text(daemon, "bien ca.")
    assert daemon.corrector.sentences == ["bien ça."]


def test_the_buffer_is_empty_after_the_sentence_check(daemon):
    type_text(daemon, "ca va bien.")
    assert daemon.buffer.current_sentence == ""
    assert daemon.buffer.current_word == ""


def test_grammar_findings_are_applied_to_the_whole_sentence(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert ("type", "Le chien.") in daemon.injector.calls


def test_a_grammar_rewrite_of_the_first_word_backspaces_over_the_whole_sentence(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert daemon.injector.calls == [("bs", len("la chien.")), ("type", "Le chien.")]


def test_a_grammar_rewrite_only_retypes_from_the_first_changed_character(daemon):
    class Correction:
        start, end, replacement = 3, 8, "chien"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "le chein.")
    # "le ch" is unchanged; "ein." goes, "ien." comes back.
    assert daemon.injector.calls == [("bs", 4), ("type", "ien.")]


def test_two_grammar_findings_at_different_offsets_are_applied_in_one_rewrite(daemon):
    class First:
        start, end, replacement = 0, 2, "Les"

    class Second:
        start, end, replacement = 9, 12, "vont"

    daemon.corrector.sentence_corrections = [First(), Second()]
    type_text(daemon, "la chien vas.")
    # The first replacement grows the text; the second offset must still land
    # on "vas", which it only does when the edits are applied right-to-left.
    assert daemon.injector.calls == [("bs", len("la chien vas.")), ("type", "Les chien vont.")]


def test_undo_after_a_grammar_rewrite_puts_the_whole_sentence_back(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "Le chien.", "la chien.")]


def test_undo_after_a_grammar_rewrite_reverts_to_the_screen_text_not_the_raw_typing(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la ca.")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "Le ça.", "la ça.")]


def test_grammar_can_be_turned_off(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.config.grammar = False
    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert not any(call[0] == "type" for call in daemon.injector.calls)


def test_a_grammar_finding_that_changes_nothing_is_skipped(daemon):
    class Correction:
        start, end, replacement = 0, 2, "la"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert daemon.injector.calls == []


def test_reset_actions_discard_the_pending_word(daemon):
    type_text(daemon, "ca")
    send(daemon, KeyEvent(action=KeyAction.RESET))
    type_text(daemon, " ")
    assert daemon.injector.calls == []


def test_backspace_rewinds_the_pending_word(daemon):
    type_text(daemon, "cax")
    send(daemon, KeyEvent(action=KeyAction.BACKSPACE))
    type_text(daemon, " ")
    assert daemon.injector.calls == [("replace", "ca ", "ça ")]


def test_a_non_french_layout_pauses_corrections(daemon):
    """The layout gate sits in the consume loop, not in the key handler."""

    daemon._is_french = False
    daemon.capture = FakeCapture(
        [
            KeyEvent(action=KeyAction.CHAR, evdev_keycode=ord("c")),
            KeyEvent(action=KeyAction.CHAR, evdev_keycode=ord("a")),
            KeyEvent(action=KeyAction.SPACE),
        ]
    )
    asyncio.run(daemon._consume_events())
    assert daemon.injector.calls == []


def test_a_french_layout_lets_the_same_keystrokes_through(daemon):
    daemon._is_french = True
    daemon.capture = FakeCapture(
        [
            KeyEvent(action=KeyAction.CHAR, evdev_keycode=ord("c")),
            KeyEvent(action=KeyAction.CHAR, evdev_keycode=ord("a")),
            KeyEvent(action=KeyAction.SPACE),
        ]
    )
    asyncio.run(daemon._consume_events())
    assert daemon.injector.calls == [("replace", "ca ", "ça ")]


async def _one_checker_tick(daemon):
    task = asyncio.create_task(daemon._layout_checker())
    await asyncio.sleep(0.01)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_a_layout_switch_seen_by_the_checker_changes_what_keystrokes_translate_to(
    monkeypatch,
):
    """Real translator, fake session: us active at start, switched to fr
    without any keystroke in between. The periodic check must both re-enable
    corrections and make the next keystroke translate as AZERTY."""

    backend = FakeBackend(codes=("us", "fr"), index=0)
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: backend)
    monkeypatch.setattr("frfix.daemon.load_config", lambda: _config())
    monkeypatch.setattr("frfix.daemon.TextInjector", lambda: FakeInjector())
    monkeypatch.setattr("frfix.daemon.KeystrokeCapture", lambda: object())
    monkeypatch.setattr("frfix.daemon.FrenchCorrector", lambda user_words=None: FakeCorrector())
    monkeypatch.setattr("frfix.daemon.LAYOUT_CHECK_INTERVAL", 0)
    daemon = FrfixDaemon()
    daemon._is_french = daemon.translator.is_french()
    assert daemon._is_french is False
    assert daemon.translator.translate(16) == "q"

    backend._index = 1
    asyncio.run(_one_checker_tick(daemon))
    assert daemon._is_french is True
    assert daemon.translator.translate(16) == "a"


def _real_daemon(monkeypatch, backend, **kwargs):
    """A daemon with a real translator on top of `backend`; everything else fake."""
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: backend)
    monkeypatch.setattr("frfix.daemon.load_config", lambda: _config())
    monkeypatch.setattr("frfix.daemon.TextInjector", lambda: FakeInjector())
    monkeypatch.setattr("frfix.daemon.KeystrokeCapture", lambda: object())
    monkeypatch.setattr("frfix.daemon.FrenchCorrector", lambda user_words=None: FakeCorrector())
    monkeypatch.setattr("frfix.daemon.LAYOUT_CHECK_INTERVAL", 0)
    return FrfixDaemon(**kwargs)


def _hypr_devices(main: str) -> str:
    """Two Hyprland 'keyboards': the real one (French) and a power button
    Hyprland also lists, still on layout[0] because it never sees the layout
    hotkey. `main` names whichever last produced input."""
    return json.dumps({"keyboards": [
        {"name": name, "main": name == main, "layout": "us,fr",
         "active_keymap": keymap}
        for name, keymap in (("power-button", "English (US)"), ("real", "French"))
    ]})


def test_the_startup_window_self_corrects_on_the_first_real_key(monkeypatch):
    """frfix starts as a user service, before any keypress, so Hyprland's
    "main" may be a non-keyboard endpoint pinned at layout[0]. The first real
    key moves "main" to the user's keyboard; that is the device to trust,
    and a later wtype-induced flip must not undo it."""

    monkeypatch.setattr(layout_mod, "_xkb_descriptions",
                        lambda: {"fr": "French", "us": "English (US)"})
    monkeypatch.setattr(layout_mod, "hyprland_signature", lambda: "sig")
    backend = HyprlandBackend()
    backend._hyprctl = lambda *a, **k: _hypr_devices(main="power-button")
    daemon = _real_daemon(monkeypatch, backend)
    daemon._is_french = daemon.translator.is_french()
    assert daemon._is_french is False

    backend._hyprctl = lambda *a, **k: _hypr_devices(main="real")
    daemon.capture = FakeCapture([KeyEvent(action=KeyAction.CHAR, evdev_keycode=16)])
    asyncio.run(daemon._consume_events())
    assert backend._trusted is True
    assert backend._device == "real"
    asyncio.run(_one_checker_tick(daemon))
    assert daemon._is_french is True

    backend._hyprctl = lambda *a, **k: _hypr_devices(main="power-button")
    asyncio.run(_one_checker_tick(daemon))
    assert daemon._is_french is True


class _SlowCapture:
    """Switches the session's layout once the daemon is up, then types one
    key late enough for the layout checker to have ticked."""

    def __init__(self, backend):
        self._backend = backend

    async def events(self):
        self._backend._index = 1
        await asyncio.sleep(0.01)
        yield KeyEvent(action=KeyAction.CHAR, evdev_keycode=16)


def test_no_layout_check_still_translates_against_the_live_layout(monkeypatch):
    """--no-layout-check only disables the French gate. The keymap group
    must still follow a real layout switch made after startup, as it did
    when translate() queried the backend per keystroke."""

    backend = FakeBackend(codes=("us", "fr"), index=0)
    daemon = _real_daemon(monkeypatch, backend, skip_layout_check=True)
    daemon.capture = _SlowCapture(backend)
    asyncio.run(daemon.run())
    assert daemon._is_french is True
    assert daemon.buffer.current_word == "a"  # AZERTY, not "q"


def test_undo_puts_the_original_word_back(daemon):
    type_text(daemon, "ca ")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "ça ", "ca ")]


def test_undo_after_a_punctuation_correction_backspaces_over_the_punctuation_too(daemon):
    type_text(daemon, "ca,")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "ça,", "ca,")]


def test_typing_on_after_a_correction_disarms_undo(daemon):
    type_text(daemon, "ca v")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == []


@pytest.mark.parametrize("action", [KeyAction.BACKSPACE, KeyAction.RESET, KeyAction.SPACE])
def test_any_key_that_moves_the_caret_after_a_correction_disarms_undo(daemon, action):
    """Backspace, arrows/shortcuts (RESET) and a bare space all move the
    caret away from the correction; undoing after them would eat other text."""
    type_text(daemon, "un ca ")
    send(daemon, KeyEvent(action=action))
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == []


def test_undo_without_a_correction_does_nothing(daemon):
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == []


def test_undo_only_reverts_the_most_recent_correction(daemon):
    type_text(daemon, "ca cest ")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "c'est ", "cest ")]


def test_a_keystroke_with_no_character_is_ignored(daemon):
    send(daemon, KeyEvent(action=KeyAction.CHAR, evdev_keycode=0))
    type_text(daemon, " ")
    assert daemon.injector.calls == []
