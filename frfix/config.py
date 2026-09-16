"""Configuration for frfix."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "frfix"
CONFIG_FILE = CONFIG_DIR / "frfix.toml"
USER_DICT_FILE = CONFIG_DIR / "dictionary.txt"

DEFAULT_CONFIG = """\
[general]
# Switch the keyboard to French when the daemon starts. Off by default: as a
# login service this would override the layout you actually chose. With it off,
# frfix stays idle until you switch to French yourself.
auto_switch_layout = false

[corrections]
spelling = true
grammar = true
"""


@dataclass
class Config:
    auto_switch_layout: bool = False
    spelling: bool = True
    grammar: bool = True
    user_words: set[str] = field(default_factory=set)


def load_config() -> Config:
    cfg = Config()

    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
    else:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
        gen = data.get("general", {})
        cfg.auto_switch_layout = gen.get("auto_switch_layout", cfg.auto_switch_layout)
        corr = data.get("corrections", {})
        cfg.spelling = corr.get("spelling", cfg.spelling)
        cfg.grammar = corr.get("grammar", cfg.grammar)

    if USER_DICT_FILE.exists():
        cfg.user_words = set(
            w.strip() for w in USER_DICT_FILE.read_text().splitlines() if w.strip()
        )

    return cfg
