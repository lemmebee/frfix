"""Characterization tests for layout detection."""

import json

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


def _hypr_devices(*keyboards: tuple[str, bool, str]) -> str:
    return json.dumps({"keyboards": [
        {"name": name, "main": main, "layout": "fr,us", "active_keymap": keymap}
        for name, main, keymap in keyboards
    ]})


def test_hyprland_follows_main_until_the_first_real_key(hyprland, descriptions):
    # At startup (a user service, before any keypress) "main" can be any of
    # the endpoints Hyprland calls keyboards: power-button, headphone jack...
    # Those never see the layout hotkey, so they must not be pinned.
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("power-button", True, "English (US)"), ("real", False, "French"))
    assert hyprland.current_index() == 1
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("power-button", False, "English (US)"), ("real", True, "French"))
    assert hyprland.current_index() == 0
    assert hyprland._device == "real"


def test_hyprland_pins_the_keyboard_seen_at_the_first_real_key(hyprland, descriptions):
    # After an injection Hyprland flips "main" to another device (a real USB
    # endpoint, here "media"), whose layout state can be stale. Keep trusting
    # the keyboard the first real key resolved.
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", True, "French"), ("media", False, "English (US)"))
    hyprland.saw_real_key()
    assert hyprland._trusted is True
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", False, "French"), ("media", True, "English (US)"))
    assert hyprland.current_index() == 0
    assert hyprland._device == "real"


def test_hyprland_does_not_pin_on_a_failed_read(hyprland):
    hyprland._hyprctl = lambda *a, **k: None
    hyprland.saw_real_key()
    assert hyprland._trusted is False


def test_hyprland_switches_the_pinned_keyboard_even_after_main_flipped(hyprland, descriptions):
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", True, "French"), ("media", False, "French"))
    hyprland.saw_real_key()
    calls = []

    def flipped(args, timeout=1.0):
        calls.append(args)
        return _hypr_devices(("real", False, "French"), ("media", True, "French"))

    hyprland._hyprctl = flipped
    assert hyprland.set_index(1)
    assert calls[-1] == ["switchxkblayout", "real", "1"]


def test_hyprland_re_resolves_when_the_pinned_keyboard_disappears(hyprland, descriptions):
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", True, "French"), ("media", False, "English (US)"))
    hyprland.saw_real_key()
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("media", False, "English (US)"), ("laptop", True, "English (US)"))
    assert hyprland.current_index() == 1
    assert hyprland._device == "laptop"


def test_hyprland_still_sees_a_real_layout_switch_on_the_pinned_keyboard(
    hyprland, descriptions
):
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", True, "French"), ("media", False, "French"))
    hyprland.saw_real_key()
    assert hyprland.current_index() == 0
    hyprland._hyprctl = lambda *a, **k: _hypr_devices(
        ("real", True, "English (US)"), ("media", False, "French"))
    assert hyprland.current_index() == 1


SWAY_INPUTS = """
[
  {"type": "pointer"},
  {"type": "keyboard",
   "identifier": "1:1:real-keyboard",
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


def _sway_devices(*keyboards: tuple[str, str, list[str], int]) -> str:
    """Build get_inputs JSON. Each tuple: (identifier, name, layouts, index)."""
    import json as _json
    devices = [
        {
            "type": "keyboard",
            "identifier": ident,
            "name": name,
            "xkb_layout_names": layouts,
            "xkb_active_layout_index": index,
        }
        for ident, name, layouts, index in keyboards
    ]
    return _json.dumps(devices)


def test_sway_picks_the_first_keyboard_until_a_real_key_is_seen():
    backend = SwayBackend()
    backend._swaymsg = lambda args, timeout=1.0: _sway_devices(
        ("virtual", "injector", ["French"], 0), ("real", "keyboard", ["French"], 0)
    )
    assert backend.current_index() == 0


def test_sway_pins_the_keyboard_seen_at_the_first_real_key():
    backend = SwayBackend()
    backend._swaymsg = lambda args, timeout=1.0: _sway_devices(
        ("real", "keyboard", ["French", "English (US)"], 0),
        ("virtual", "injector", ["French", "English (US)"], 1),
    )
    backend.saw_real_key()
    assert backend.current_index() == 0
    # A later get_inputs call where a virtual/injector device sorts first
    # (or reports a different index) must not move the pin.
    backend._swaymsg = lambda args, timeout=1.0: _sway_devices(
        ("virtual", "injector", ["French", "English (US)"], 1),
        ("real", "keyboard", ["French", "English (US)"], 0),
    )
    assert backend.current_index() == 0


def test_sway_does_not_pin_on_a_failed_read():
    backend = SwayBackend()
    backend._swaymsg = lambda args, timeout=1.0: None
    backend.saw_real_key()
    assert backend._trusted is False


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
