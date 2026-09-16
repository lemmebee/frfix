"""End-to-end tests for the daemon's correction pipeline."""

import asyncio

import pytest

from frfix.capture import KeyAction, KeyEvent
from frfix.daemon import FrfixDaemon


class FakeInjector:
    backend_name = "fake"

    def __init__(self):
        self.calls = []

    def send_backspaces(self, count):
        self.calls.append(("bs", count))

    def send_string(self, text):
        self.calls.append(("type", text))

    def replace_word(self, old_word, new_word, extra_backspaces=0):
        self.calls.append(("replace", old_word, new_word, extra_backspaces))


class FakeCorrector:
    def __init__(self, words=None, sentence_corrections=None):
        self.words = words or {}
        self.sentence_corrections = sentence_corrections or []
        self.checked = []

    def check_word(self, word):
        self.checked.append(word)
        return self.words.get(word)

    def check_sentence(self, sentence):
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
    assert daemon.injector.calls == [("replace", "ca", "ça", 1)]


def test_nothing_is_injected_while_the_word_is_still_being_typed(daemon):
    type_text(daemon, "ca")
    assert daemon.injector.calls == []


def test_a_correct_word_is_left_alone(daemon):
    type_text(daemon, "bonjour ")
    assert daemon.injector.calls == []


def test_each_word_is_corrected_independently(daemon):
    type_text(daemon, "ca cest ")
    assert daemon.injector.calls == [
        ("replace", "ca", "ça", 1),
        ("replace", "cest", "c'est", 1),
    ]


def test_punctuation_also_completes_a_word(daemon):
    type_text(daemon, "ca,")
    assert daemon.injector.calls == [("replace", "ca", "ça", 1)]


def test_spelling_can_be_turned_off(daemon):
    daemon.config.spelling = False
    type_text(daemon, "ca ")
    assert daemon.injector.calls == []


def test_a_correction_identical_to_the_typed_word_is_not_injected(daemon):
    daemon.corrector.words = {"ca": "ca"}
    type_text(daemon, "ca ")
    assert daemon.injector.calls == []


def test_a_sentence_ending_corrects_the_final_word(daemon):
    type_text(daemon, "ca.")
    assert ("replace", "ca", "ça", 1) in daemon.injector.calls


def test_grammar_findings_are_applied_to_the_whole_sentence(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert ("type", "Le chien.") in daemon.injector.calls


def test_a_grammar_rewrite_backspaces_over_the_whole_sentence(daemon):
    class Correction:
        start, end, replacement = 0, 2, "Le"

    daemon.corrector.sentence_corrections = [Correction()]
    type_text(daemon, "la chien.")
    assert ("bs", len("la chien.")) in daemon.injector.calls


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
    assert daemon.injector.calls == [("replace", "ca", "ça", 1)]


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
    assert daemon.injector.calls == [("replace", "ca", "ça", 1)]


def test_undo_puts_the_original_word_back(daemon):
    type_text(daemon, "ca ")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "ça", "ca", 0)]


def test_undo_without_a_correction_does_nothing(daemon):
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == []


def test_undo_only_reverts_the_most_recent_correction(daemon):
    type_text(daemon, "ca cest ")
    daemon.injector.calls.clear()
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    send(daemon, KeyEvent(action=KeyAction.UNDO))
    assert daemon.injector.calls == [("replace", "c'est", "cest", 0)]


def test_a_keystroke_with_no_character_is_ignored(daemon):
    send(daemon, KeyEvent(action=KeyAction.CHAR, evdev_keycode=0))
    type_text(daemon, " ")
    assert daemon.injector.calls == []
