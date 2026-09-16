"""Characterization tests for layout detection."""

import pytest

from frfix import layout as layout_mod
from frfix.layout import (
    EnvBackend,
    GnomeBackend,
    HyprlandBackend,
    LayoutBackend,
    SwayBackend,
    XkbBackend,
    detect_backend,
    is_french_code,
)


@pytest.mark.parametrize("code", ["fr", "be", "ca(fr)", "ch(fr)", "fr:2"])
def test_french_layout_codes_are_recognised(code):
    assert is_french_code(code) is True


@pytest.mark.parametrize("code", ["us", "de", "gb", "ca", "ch", ""])
def test_other_layout_codes_are_not_french(code):
    assert is_french_code(code) is False


@pytest.fixture
def descriptions(monkeypatch):
    table = {"fr": "French", "us": "English (US)", "de": "German"}
    monkeypatch.setattr(layout_mod, "_xkb_descriptions", lambda: table)
    return table


def test_an_exact_description_maps_back_to_its_code(descriptions):
    assert layout_mod._code_for_description("French") == "fr"


def test_a_description_with_an_appended_variant_still_maps_back(descriptions):
    assert layout_mod._code_for_description("French (AZERTY)") == "fr"


def test_an_unknown_description_maps_to_nothing(descriptions):
    assert layout_mod._code_for_description("Klingon") is None


def test_an_empty_description_maps_to_nothing(descriptions):
    assert layout_mod._code_for_description("") is None


def test_the_base_backend_answers_nothing():
    backend = LayoutBackend()
    assert backend.available() is False
    assert backend.layouts() == []
    assert backend.current_index() == 0
    assert backend.set_index(0) is False
    assert backend.variants() == ""
    assert backend.options() == ""


def test_detect_backend_falls_back_to_the_inert_backend(monkeypatch):
    monkeypatch.setattr(layout_mod, "BACKENDS", ())
    assert detect_backend().name == "none"


def test_detect_backend_returns_the_first_available_one(monkeypatch):
    class No(LayoutBackend):
        name = "no"

        def available(self):
            return False

    class Yes(LayoutBackend):
        name = "yes"

        def available(self):
            return True

    monkeypatch.setattr(layout_mod, "BACKENDS", (No, Yes))
    assert detect_backend().name == "yes"


def test_a_backend_that_raises_while_probing_is_skipped(monkeypatch):
    class Boom(LayoutBackend):
        name = "boom"

        def available(self):
            raise OSError("no session")

    class Fine(LayoutBackend):
        name = "fine"

        def available(self):
            return True

    monkeypatch.setattr(layout_mod, "BACKENDS", (Boom, Fine))
    assert detect_backend().name == "fine"


def test_the_probe_order_prefers_compositors_over_the_environment():
    assert layout_mod.BACKENDS == (
        HyprlandBackend,
        SwayBackend,
        GnomeBackend,
        XkbBackend,
        EnvBackend,
    )


HYPR_DEVICES = """
{"keyboards": [
  {"name": "kb0", "main": false, "layout": "us", "active_keymap": "English (US)"},
  {"name": "kb1", "main": true, "layout": "fr,us", "active_keymap": "English (US)"}
]}
"""


@pytest.fixture
def hyprland(monkeypatch):
    monkeypatch.setattr(layout_mod, "hyprland_signature", lambda: "sig")
    backend = HyprlandBackend()
    monkeypatch.setattr(backend, "_hyprctl", lambda args, timeout=1.0: HYPR_DEVICES)
    return backend


def test_hyprland_reads_layouts_from_the_main_keyboard(hyprland, descriptions):
    assert hyprland.layouts() == ["fr", "us"]


def test_hyprland_maps_the_active_keymap_to_an_index(hyprland, descriptions):
    assert hyprland.current_index() == 1


def test_hyprland_reports_the_first_layout_when_the_keymap_is_unknown(
    hyprland, monkeypatch
):
    monkeypatch.setattr(layout_mod, "_xkb_descriptions", lambda: {})
    assert hyprland.current_index() == 0


def test_hyprland_survives_unparseable_output(monkeypatch):
    monkeypatch.setattr(layout_mod, "hyprland_signature", lambda: "sig")
    backend = HyprlandBackend()
    monkeypatch.setattr(backend, "_hyprctl", lambda args, timeout=1.0: "not json")
    assert backend.layouts() == []
    assert backend.current_index() == 0


def test_hyprland_treats_an_unset_option_as_empty(monkeypatch):
    monkeypatch.setattr(layout_mod, "hyprland_signature", lambda: "sig")
    backend = HyprlandBackend()
    monkeypatch.setattr(
        backend, "_hyprctl", lambda args, timeout=1.0: '{"str": "[[EMPTY]]"}'
    )
    assert backend.variants() == ""
    assert backend.options() == ""


SWAY_INPUTS = """
[
  {"type": "pointer"},
  {"type": "keyboard",
   "xkb_layout_names": ["French", "English (US)"],
   "xkb_active_layout_index": 1}
]
"""


@pytest.fixture
def sway(monkeypatch):
    monkeypatch.setattr(layout_mod, "sway_socket", lambda: "/tmp/sway.sock")
    backend = SwayBackend()
    monkeypatch.setattr(backend, "_swaymsg", lambda args, timeout=1.0: SWAY_INPUTS)
    return backend


def test_sway_turns_display_names_back_into_codes(sway, descriptions):
    assert sway.layouts() == ["fr", "us"]


def test_sway_keeps_a_display_name_it_cannot_map(sway, monkeypatch):
    monkeypatch.setattr(layout_mod, "_xkb_descriptions", lambda: {})
    assert sway.layouts() == ["French", "English (US)"]


def test_sway_reads_the_active_index_directly(sway):
    assert sway.current_index() == 1


def test_sway_survives_unparseable_output(monkeypatch):
    monkeypatch.setattr(layout_mod, "sway_socket", lambda: "/tmp/sway.sock")
    backend = SwayBackend()
    monkeypatch.setattr(backend, "_swaymsg", lambda args, timeout=1.0: "not json")
    assert backend.layouts() == []
    assert backend.current_index() == 0


def test_gnome_pulls_codes_out_of_the_gsettings_tuple_list(monkeypatch):
    monkeypatch.setattr(
        layout_mod, "_run", lambda *a, **k: "[('xkb', 'fr'), ('xkb', 'us')]"
    )
    assert GnomeBackend().layouts() == ["fr", "us"]


def test_gnome_reads_the_current_index_from_a_uint32(monkeypatch):
    monkeypatch.setattr(layout_mod, "_run", lambda *a, **k: "uint32 1")
    assert GnomeBackend().current_index() == 1


def test_gnome_falls_back_to_the_first_layout_on_junk(monkeypatch):
    monkeypatch.setattr(layout_mod, "_run", lambda *a, **k: "nonsense")
    assert GnomeBackend().current_index() == 0


SETXKBMAP_QUERY = """rules:      evdev
model:      pc105
layout:     fr,us
variant:    azerty,
options:    grp:alt_shift_toggle
"""


def test_xkb_parses_the_setxkbmap_query(monkeypatch):
    monkeypatch.setattr(layout_mod, "_run", lambda *a, **k: SETXKBMAP_QUERY)
    backend = XkbBackend()
    assert backend.layouts() == ["fr", "us"]
    assert backend.variants() == "azerty,"
    assert backend.options() == "grp:alt_shift_toggle"


def test_xkb_reports_nothing_when_setxkbmap_is_unavailable(monkeypatch):
    monkeypatch.setattr(layout_mod, "_run", lambda *a, **k: None)
    assert XkbBackend().layouts() == []


def test_xkb_refuses_an_out_of_range_switch(monkeypatch):
    monkeypatch.setattr(layout_mod, "_run", lambda *a, **k: SETXKBMAP_QUERY)
    assert XkbBackend().set_index(5) is False


def test_env_backend_reads_the_xkb_defaults(monkeypatch):
    monkeypatch.setenv("XKB_DEFAULT_LAYOUT", "fr,us")
    monkeypatch.setenv("XKB_DEFAULT_VARIANT", "azerty")
    monkeypatch.setenv("XKB_DEFAULT_OPTIONS", "grp:alt_shift_toggle")
    backend = EnvBackend()
    assert backend.available() is True
    assert backend.layouts() == ["fr", "us"]
    assert backend.variants() == "azerty"
    assert backend.options() == "grp:alt_shift_toggle"


def test_env_backend_is_unavailable_without_a_default_layout(monkeypatch):
    monkeypatch.delenv("XKB_DEFAULT_LAYOUT", raising=False)
    assert EnvBackend().available() is False
