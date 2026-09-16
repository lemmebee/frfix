"""Characterization tests for text injection."""

import pytest

from frfix import injector as injector_mod
from frfix.injector import TextInjector


@pytest.fixture
def commands(monkeypatch):
    recorded = []

    def fake_run(args, **kwargs):
        recorded.append(list(args))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(injector_mod.subprocess, "run", fake_run)
    return recorded


def names(backends=injector_mod.BACKENDS):
    return [b[0] for b in backends]


def test_the_probe_order_puts_wayland_first():
    assert names() == ["wtype", "xdotool", "ydotool"]


def test_wayland_is_preferred_over_x11(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(injector_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert TextInjector().backend_name == "wtype"


def test_x11_is_used_when_there_is_no_wayland_socket(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(injector_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert TextInjector().backend_name == "xdotool"


def test_no_usable_backend_is_a_setup_error_with_instructions(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(injector_mod.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as excinfo:
        TextInjector()
    assert "wtype" in str(excinfo.value)
    assert "xdotool" in str(excinfo.value)


def test_a_backend_whose_probe_raises_is_skipped(monkeypatch):
    def boom():
        raise OSError("no session")

    monkeypatch.setattr(
        injector_mod,
        "BACKENDS",
        (("boom", boom, None, None), ("fine", lambda: True, lambda c: None, lambda t: None)),
    )
    assert TextInjector().backend_name == "fine"


def test_wtype_needs_both_a_wayland_socket_and_the_binary(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr(injector_mod.shutil, "which", lambda name: None)
    assert injector_mod._wtype_available() is False


def test_ydotool_is_unavailable_without_the_binary(monkeypatch):
    monkeypatch.setattr(injector_mod.shutil, "which", lambda name: None)
    assert injector_mod._ydotool_available() is False


def _forced_injector(monkeypatch, name):
    monkeypatch.setattr(
        injector_mod, "BACKENDS", tuple(b for b in injector_mod.BACKENDS if b[0] == name)
    )
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(injector_mod.shutil, "which", lambda n: f"/usr/bin/{n}")
    return TextInjector()


def test_wtype_sends_one_keystroke_per_backspace(commands, monkeypatch):
    _forced_injector(monkeypatch, "wtype").send_backspaces(2)
    assert commands == [["wtype", "-k", "BackSpace", "-k", "BackSpace"]]


def test_wtype_passes_text_after_a_separator(commands, monkeypatch):
    _forced_injector(monkeypatch, "wtype").send_string("-ça")
    assert commands == [["wtype", "--", "-ça"]]


def test_xdotool_releases_modifiers_before_backspacing(commands, monkeypatch):
    _forced_injector(monkeypatch, "xdotool").send_backspaces(1)
    assert commands[0][:2] == ["xdotool", "keyup"]
    assert commands[1] == ["xdotool", "key", "BackSpace"]


def test_xdotool_types_without_delay(commands, monkeypatch):
    _forced_injector(monkeypatch, "xdotool").send_string("ça")
    assert commands == [["xdotool", "type", "--delay", "0", "--", "ça"]]


def test_ydotool_sends_a_press_and_release_per_backspace(commands, monkeypatch):
    injector = _forced_injector(monkeypatch, "ydotool")
    commands.clear()
    injector.send_backspaces(2)
    assert commands == [["ydotool", "key", "14:1", "14:0", "14:1", "14:0"]]


def test_ydotool_types_without_delay(commands, monkeypatch):
    injector = _forced_injector(monkeypatch, "ydotool")
    commands.clear()
    injector.send_string("ça")
    assert commands == [["ydotool", "type", "--key-delay", "0", "--", "ça"]]


@pytest.fixture
def injector(monkeypatch):
    return _forced_injector(monkeypatch, "wtype")


def test_replacing_a_word_typed_before_a_space_restores_the_space(commands, injector):
    injector.replace_word("ca", "ça", extra_backspaces=1)
    assert commands == [
        ["wtype", "-k", "BackSpace", "-k", "BackSpace", "-k", "BackSpace"],
        ["wtype", "--", "ça"],
        ["wtype", "--", " "],
    ]


def test_replacing_a_word_with_no_separator_adds_none(commands, injector):
    injector.replace_word("ca", "ça", extra_backspaces=0)
    assert commands == [
        ["wtype", "-k", "BackSpace", "-k", "BackSpace"],
        ["wtype", "--", "ça"],
    ]


def test_zero_backspaces_sends_no_command(commands, injector):
    injector.send_backspaces(0)
    injector.send_backspaces(-1)
    assert commands == []


def test_empty_text_sends_no_command(commands, injector):
    injector.send_string("")
    assert commands == []
