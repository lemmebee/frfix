"""Characterization tests for evdev keycode to character translation."""

import pytest

from frfix import layout as layout_mod
from frfix.xchar import KeyTranslator, _level


class FakeBackend(layout_mod.LayoutBackend):
    """A layout backend with a fixed answer, so tests need no real session."""

    name = "fake"

    def __init__(self, codes=("fr",), index=0):
        self._codes = list(codes)
        self._index = index
        self.set_calls = []

    def available(self):
        return True

    def layouts(self):
        return list(self._codes)

    def current_index(self):
        return self._index

    def set_index(self, index):
        self.set_calls.append(index)
        self._index = index
        return True


@pytest.fixture
def translator(monkeypatch):
    backend = FakeBackend(codes=("fr", "us"))
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: backend)
    return KeyTranslator()


@pytest.mark.parametrize(
    "shift, altgr, expected",
    [(False, False, 0), (True, False, 1), (False, True, 2), (True, True, 3)],
)
def test_level_encodes_the_modifier_combination(shift, altgr, expected):
    assert _level(shift, altgr) == expected


def test_active_layout_follows_the_backend_index(translator):
    assert translator.active_layout() == "fr"
    translator._backend._index = 1
    assert translator.active_layout() == "us"


def test_is_french_tracks_the_active_layout(translator):
    assert translator.is_french() is True
    translator._backend._index = 1
    assert translator.is_french() is False


def test_an_out_of_range_index_reports_no_layout(translator):
    translator._backend._index = 7
    assert translator.active_layout() == ""
    assert translator.is_french() is False


def test_forced_layout_overrides_the_session(monkeypatch):
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: FakeBackend(("us",), 0))
    trans = KeyTranslator(force_layout="fr")
    assert trans.active_layout() == "fr"
    assert trans.is_french() is True


def test_switch_to_returns_the_previous_index_and_applies_it(translator):
    translator._backend._index = 1
    assert translator.switch_to("fr") == 1
    assert translator._backend.set_calls == [0]


def test_switch_to_the_active_layout_is_a_no_op(translator):
    assert translator.switch_to("fr") is None
    assert translator._backend.set_calls == []


def test_switch_to_an_unconfigured_layout_is_refused(translator):
    assert translator.switch_to("de") is None
    assert translator._backend.set_calls == []


def test_restore_puts_the_index_back(translator):
    translator.restore(1)
    assert translator._backend.set_calls == [1]


def test_switch_to_records_the_new_group_without_re_observing(translator):
    translator.switch_to("us")
    translator._backend._index = 0          # a backend that would now answer differently
    assert translator._group() == 1


def test_restore_records_the_restored_group_without_re_observing(translator):
    translator.restore(1)
    translator._backend._index = 0
    assert translator._group() == 1


AZERTY_CASES = [
    (16, False, False, "a"),
    (16, True, False, "A"),
    (17, False, False, "z"),
    (30, False, False, "q"),
    (39, False, False, "m"),
    (3, False, False, "é"),
    (3, True, False, "2"),
    (10, False, False, "ç"),
    (18, False, True, "€"),
]


@pytest.mark.parametrize("keycode, shift, altgr, expected", AZERTY_CASES)
def test_the_active_keymap_produces_french_characters(
    translator, keycode, shift, altgr, expected
):
    assert translator.translate(keycode, shift=shift, altgr=altgr) == expected


def test_an_unmapped_keycode_translates_to_nothing(translator):
    assert translator.translate(9999) is None


def test_the_active_keymap_falls_back_to_the_base_level(translator):
    """An unshifted character is reported even when shift is held on a key
    that has no shifted form of its own."""
    assert translator.translate(16, shift=True) == "A"


def test_a_forced_layout_translates_against_that_layout(monkeypatch):
    """With fr second in the list, forcing it must not translate against us."""

    monkeypatch.setattr(layout_mod, "detect_backend", lambda: FakeBackend(("us", "fr"), 0))
    trans = KeyTranslator(force_layout="fr")
    assert trans._group() == 1
    assert trans.translate(16) == "a"      # AZERTY a, us would give q
    assert trans.translate(30) == "q"      # AZERTY q, us would give a


def test_a_forced_layout_absent_from_the_session_uses_the_first_group(monkeypatch):
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: FakeBackend(("us",), 0))
    trans = KeyTranslator(force_layout="de")
    assert trans._group() == 0


def test_the_translation_group_follows_the_last_observed_layout(translator):
    assert translator._group() == 0
    translator._backend._index = 1
    translator.active_layout()
    assert translator._group() == 1


def test_an_out_of_range_active_index_translates_against_the_first_group(translator):
    translator._backend._index = 9
    translator.active_layout()
    assert translator._group() == 0


class CountingBackend(FakeBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queries = 0

    def layouts(self):
        self.queries += 1
        return super().layouts()

    def current_index(self):
        self.queries += 1
        return super().current_index()


def test_translate_never_asks_the_backend_which_group_is_active(monkeypatch):
    """The backend is a subprocess spawn on Hyprland: querying it per keystroke
    is slow and, worse, can sample a different state than the daemon's layout
    check saw. Keystrokes must translate against the last observed state."""

    backend = CountingBackend(codes=("fr", "us"))
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: backend)
    trans = KeyTranslator()
    trans.is_french()
    before = backend.queries
    for _ in range(50):
        trans.translate(16)
    assert backend.queries == before


def test_a_layout_switch_takes_effect_once_observed(translator):
    assert translator.translate(16) == "a"      # AZERTY
    translator._backend._index = 1              # session switched to us
    assert translator.translate(16) == "a"      # not observed yet: unchanged
    translator.is_french()                      # what the daemon polls
    assert translator.translate(16) == "q"      # QWERTY


def test_source_names_the_active_keymap(translator):
    assert translator.source == "xkbcommon"


def test_close_drops_the_keymap(translator):
    translator.close()
    assert translator._keymap is None


def test_an_unusable_keymap_raises_at_construction_instead_of_mistranslating(monkeypatch):
    backend = FakeBackend(codes=("nonexistent-layout-xyz",))
    monkeypatch.setattr(layout_mod, "detect_backend", lambda: backend)
    with pytest.raises(RuntimeError):
        KeyTranslator()
