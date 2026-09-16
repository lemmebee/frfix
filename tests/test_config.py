"""Characterization tests for configuration loading."""

import pytest

from frfix import config as config_mod
from frfix.config import Config, load_config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    directory = tmp_path / "frfix"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", directory)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", directory / "frfix.toml")
    monkeypatch.setattr(config_mod, "USER_DICT_FILE", directory / "dictionary.txt")
    return directory


def write_config(config_dir, text):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "frfix.toml").write_text(text)


def test_a_first_run_writes_the_default_config_file(config_dir):
    load_config()
    assert (config_dir / "frfix.toml").read_text() == config_mod.DEFAULT_CONFIG


def test_a_first_run_returns_the_defaults(config_dir):
    assert load_config() == Config()


def test_the_defaults_enable_both_kinds_of_correction():
    cfg = Config()
    assert cfg.spelling is True
    assert cfg.grammar is True


def test_layout_switching_is_off_by_default():
    assert Config().auto_switch_layout is False


def test_the_written_defaults_parse_back_to_the_same_values(config_dir):
    load_config()
    assert load_config() == Config()


def test_settings_are_read_from_the_file(config_dir):
    write_config(
        config_dir,
        """
        [general]
        auto_switch_layout = true

        [corrections]
        spelling = false
        grammar = false
        """,
    )
    cfg = load_config()
    assert cfg.auto_switch_layout is True
    assert cfg.spelling is False
    assert cfg.grammar is False


def test_missing_sections_fall_back_to_the_defaults(config_dir):
    write_config(config_dir, "[general]\n")
    cfg = load_config()
    assert cfg.spelling is True
    assert cfg.grammar is True
    assert cfg.auto_switch_layout is False


def test_an_existing_config_file_is_not_overwritten(config_dir):
    write_config(config_dir, "[corrections]\ngrammar = false\n")
    load_config()
    assert "grammar = false" in (config_dir / "frfix.toml").read_text()


def test_the_user_dictionary_is_loaded(config_dir):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "dictionary.txt").write_text("frfix\nlemmebee\n")
    assert load_config().user_words == {"frfix", "lemmebee"}


def test_blank_lines_and_padding_in_the_dictionary_are_ignored(config_dir):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "dictionary.txt").write_text("  frfix  \n\n\n  \nlemmebee\n")
    assert load_config().user_words == {"frfix", "lemmebee"}


def test_no_dictionary_file_means_no_user_words(config_dir):
    assert load_config().user_words == set()
