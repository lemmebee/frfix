"""Configuration for frfix."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "frfix"
CONFIG_FILE = CONFIG_DIR / "frfix.toml"
USER_DICT_FILE = CONFIG_DIR / "dictionary.txt"

DEFAULT_CONFIG = """\
[general]
enabled = true

[corrections]
spelling = true
grammar = true

[overlay]
enabled = true
duration_ms = 1500
bg_color = "#1a1a2e"
text_color = "#e0e0e0"
highlight_color = "#4ecca3"

[exclusions]
apps = ["keepassxc", "1password", "bitwarden"]
window_titles = ["password", "mot de passe", "sudo"]
"""


@dataclass
class OverlayConfig:
    enabled: bool = True
    duration_ms: int = 1500
    bg_color: str = "#1a1a2e"
    text_color: str = "#e0e0e0"
    highlight_color: str = "#4ecca3"


@dataclass
class Config:
    enabled: bool = True
    spelling: bool = True
    grammar: bool = True
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    excluded_apps: list[str] = field(default_factory=lambda: ["keepassxc", "1password", "bitwarden"])
    excluded_titles: list[str] = field(default_factory=lambda: ["password", "mot de passe", "sudo"])
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
        cfg.enabled = gen.get("enabled", True)
        corr = data.get("corrections", {})
        cfg.spelling = corr.get("spelling", True)
        cfg.grammar = corr.get("grammar", True)
        ov = data.get("overlay", {})
        cfg.overlay = OverlayConfig(
            enabled=ov.get("enabled", True),
            duration_ms=ov.get("duration_ms", 1500),
            bg_color=ov.get("bg_color", "#1a1a2e"),
            text_color=ov.get("text_color", "#e0e0e0"),
            highlight_color=ov.get("highlight_color", "#4ecca3"),
        )
        exc = data.get("exclusions", {})
        cfg.excluded_apps = exc.get("apps", cfg.excluded_apps)
        cfg.excluded_titles = exc.get("window_titles", cfg.excluded_titles)

    if USER_DICT_FILE.exists():
        cfg.user_words = set(
            w.strip() for w in USER_DICT_FILE.read_text().splitlines() if w.strip()
        )

    return cfg
