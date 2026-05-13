<p align="center">
  <img src="assets/icon.svg" alt="frfix icon" width="128" height="128"/>
</p>

<h1 align="center">frfix</h1>

<p align="center">
  <em>System-wide real-time French autocorrect daemon for Linux/X11.</em>
</p>

<p align="center">
  <img alt="platform" src="https://img.shields.io/badge/platform-Linux%20%2F%20X11-blue"/>
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white"/>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green"/>
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange"/>
</p>

---

## What it is

`frfix` runs as a background daemon, watches your keystrokes via `evdev`, and silently fixes French text as you type — in any application (terminal, browser, editor, chat, IDE). No per-app extension, no clipboard hijack, no input method engine. It just fixes mistakes in place.

Think of it as a French-only, system-wide spellchecker that *acts* instead of underlining.

## What it corrects

- **Missing accents**: `francais` → `français`, `realite` → `réalité`, `ecran` → `écran`, `etre` → `être`
- **Elisions**: `cest` → `c'est`, `jai` → `j'ai`, `lhomme` → `l'homme`, `cetait` → `c'était`, `quil` → `qu'il`
- **AZERTY/QWERTY typos**: `vrqi` → `vrai`, `fqire` → `faire`, `voulqis` → `voulais` (q/a swaps and similar)
- **Grammar** at sentence boundaries: `tu peut` → `tu peux`, `je veut` → `je veux`, agreement nits
- **Undo**: hit `Ctrl+Z` immediately after a correction to revert it. Frfix tracks recent corrections in a small ring buffer.

Conservative by design — it will not touch a word that is already valid French. False positives are the enemy.

## How it works

```
                ┌──────────┐    keysym +    ┌──────────┐
   /dev/input ─▶│  evdev   │───keycode ────▶│ KeyTrans │
                │ capture  │  (read-only)   │  X11/xkb │
                └──────────┘                └────┬─────┘
                                                 │ char
                                                 ▼
                              ┌───────────────────────────────┐
                              │ TextBuffer (word + sentence)  │
                              └────────────┬──────────────────┘
                                           │ word / sentence
                                           ▼
                              ┌───────────────────────────────┐
                              │ FrenchCorrector               │
                              │  • hunspell (spelling)        │
                              │  • grammalecte (grammar)      │
                              │  • user dictionary            │
                              └────────────┬──────────────────┘
                                           │ replacement
                                           ▼
                              ┌───────────────────────────────┐
                              │ Injector (xdotool)            │
                              │  backspace × N + type fix     │
                              └───────────────────────────────┘
```

- **evdev** reads physical keystrokes system-wide. No grab — other apps still receive every key.
- **X11/xkb keysym tables** translate keycodes to characters using the currently active layout, so AZERTY and QWERTY both work.
- **hunspell** (via `hunspell-fr-comprehensive`) provides the spelling dictionary.
- **grammalecte** (optional) provides sentence-level grammar checking.
- **xdotool** types backspaces + the corrected word back into the focused window.
- Only active when the current keyboard layout is `fr`. On startup, frfix switches to `fr` and remembers the previous layout; on exit it restores it.

## Install

```bash
git clone https://github.com/lemmebee/frfix.git
cd frfix
bash setup.sh
```

`setup.sh` installs system packages (hunspell, gobject-introspection, python venv tooling, `xdotool`), adds you to the `input` group, creates a venv, and installs a systemd user unit.

> If you were just added to `input`, log out and back in before running.

## Run

```bash
# foreground
.venv/bin/frfix

# verbose: see keystrokes, candidate words, corrections
.venv/bin/frfix --debug

# skip layout detection (always correct, regardless of current layout)
.venv/bin/frfix --no-layout-check

# force a specific xkb layout name
.venv/bin/frfix --force-layout fr

# as a systemd user service (auto-start on login)
systemctl --user enable --now frfix
journalctl --user -u frfix -f      # follow logs
```

Or via `make`:

```bash
make run      # editable install + run
make debug    # editable install + run with --debug
```

## Configuration

Config file: `~/.config/frfix/frfix.toml` (auto-created with defaults on first run).

```toml
[general]
enabled = true

[corrections]
spelling = true     # word-level: accents, typos, elisions
grammar  = true     # sentence-level grammalecte rules

[overlay]
enabled       = true
duration_ms   = 1500
bg_color      = "#1a1a2e"
text_color    = "#e0e0e0"
highlight_color = "#4ecca3"

[exclusions]
apps          = ["keepassxc", "1password", "bitwarden"]
window_titles = ["password", "mot de passe", "sudo"]
```

**Custom dictionary**: `~/.config/frfix/dictionary.txt` — one word per line. Anything listed here is treated as a valid French word and never corrected. Use it for names, jargon, brand names.

**Exclusions**: focused windows whose app class or title match any pattern are skipped entirely. Password managers and `sudo` prompts are excluded by default — corrections must never touch typed secrets.

## CLI

| Flag | Meaning |
|---|---|
| `--debug` | Print each keystroke, candidate word, and correction decision to stdout. |
| `--no-layout-check` | Don't query the active xkb layout; always run corrections. Useful for non-GNOME setups. |
| `--force-layout NAME` | Use this xkb layout name for keysym translation regardless of system state. |

## Requirements

- Linux with **X11** (Wayland is not supported — Wayland blocks both `evdev`-style global capture and `xdotool` injection)
- Python **3.12+**
- `xdotool`, `hunspell-fr-comprehensive`, `x11-xkb-utils`
- User must be in the `input` group: `sudo usermod -aG input $USER` (then log out / in)

## Troubleshooting

- **`PermissionError` opening `/dev/input/event*`** — you're not in the `input` group, or you haven't logged out and back in since being added.
- **Nothing gets corrected** — check `frfix --debug`. If keystrokes don't print, evdev access is broken. If words print but corrections don't fire, hunspell isn't installed or the layout isn't `fr`.
- **Corrections fire but garble the word** — `xdotool` injection timing. Try running outside a terminal multiplexer or under a different compositor.
- **Wayland session** — not supported. Switch your session to Xorg at the login screen.
- **Wrong characters being typed** — keysym translation is using the wrong layout. Pass `--force-layout fr`.

## Project layout

```
frfix/
├── frfix/
│   ├── daemon.py      # asyncio event loop, layout monitor
│   ├── capture.py     # evdev → KeyAction events
│   ├── xchar.py       # X11/xkb keycode → char
│   ├── buffer.py      # word + sentence state machine
│   ├── corrector.py   # hunspell + grammalecte
│   ├── injector.py    # xdotool keystroke synthesis
│   ├── overlay.py     # optional GTK toast for corrections
│   └── config.py      # TOML config + user dictionary
├── systemd/frfix.service
├── assets/icon.svg
├── setup.sh
└── pyproject.toml
```

## Security model

frfix never logs keystrokes, never persists what you typed, and never sends anything over the network. The default exclusion list keeps it out of password managers and `sudo` prompts. If you type secrets in an unusual app, add it to `exclusions.apps` in the config.

## License

MIT.
