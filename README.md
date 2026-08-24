<p align="center">
  <img src="assets/icon.svg" alt="frfix icon" width="128" height="128"/>
</p>

<h1 align="center">frfix</h1>

<p align="center">
  <em>System-wide real-time French autocorrect daemon for Linux, on X11 and Wayland.</em>
</p>

<p align="center">
  <img alt="platform" src="https://img.shields.io/badge/platform-Linux%20%C2%B7%20X11%20%2B%20Wayland-blue"/>
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
                │ capture  │  (read-only)   │ xkbcommon│
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
                              │  • grammalecte speller        │
                              │  • grammalecte grammar rules  │
                              │  • user dictionary            │
                              └────────────┬──────────────────┘
                                           │ replacement
                                           ▼
                              ┌───────────────────────────────┐
                              │ Injector                      │
                              │  wtype / xdotool / ydotool    │
                              │  backspace × N + type fix     │
                              └───────────────────────────────┘
```

- **evdev** reads physical keystrokes system-wide. No grab — other apps still receive every key.
- **libxkbcommon** translates keycodes to characters using the active layout, so AZERTY and QWERTY both work. This is the same library X11 and every Wayland compositor use internally, and it needs no display-server connection.
- **grammalecte** provides both the spelling dictionary and the sentence-level grammar rules.
- **wtype / xdotool / ydotool** types backspaces + the corrected word back into the focused window, whichever is available.
- Only active when the current keyboard layout is French. frfix stays idle otherwise, and notices layout switches within two seconds.

### Portability

Nothing here is tied to a distribution or a desktop. Every piece that varies
between systems is probed at runtime and the first working option wins:

| Concern | Probe order |
|---|---|
| Layout detection | Hyprland → Sway → GNOME → X11 (`setxkbmap`) → `XKB_DEFAULT_LAYOUT` |
| Keycode → character | libxkbcommon → built-in AZERTY table |
| Injection | `wtype` (Wayland) → `xdotool` (X11) → `ydotool` (either) |
| System packages | `pacman`, `apt-get`, `dnf`, `zypper`, `apk`, `xbps`, `emerge` |

Wayland is tried before X11 for injection on purpose: on a Wayland compositor
`xdotool` only reaches XWayland clients, so corrections would silently vanish
in most applications. For the same reason the keysym table is read from
libxkbcommon rather than from the X server — XWayland is handed a fixed keymap
and never follows the compositor's layout switches.

## Install

```bash
git clone https://github.com/lemmebee/frfix.git
cd frfix
bash setup.sh
```

`setup.sh` detects your package manager, installs the system packages (python headers, a compiler, `libxkbcommon`, and `wtype`/`xdotool`), adds you to the `input` group, creates a venv, downloads the Grammalecte engine, and installs a systemd user unit pointing at this checkout.

The `grammalecte` module is not published on PyPI: `pygrammalecte` fetches it on first use. `setup.sh` does that up front, and you can redo it alone with `.venv/bin/frfix-bootstrap`.

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

# switch the keyboard to French on startup (off by default)
.venv/bin/frfix --switch-layout

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
# Switch the keyboard to French when the daemon starts, restoring the previous
# layout on exit. Off by default: as a login service this would override the
# layout you actually chose.
auto_switch_layout = false

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
| `--no-layout-check` | Don't query the active xkb layout; always run corrections. |
| `--force-layout NAME` | Use this xkb layout name for keysym translation regardless of system state. |
| `--switch-layout` | Switch the keyboard to French on startup, overriding `general.auto_switch_layout`. |

## Requirements

- Linux, **X11 or Wayland**
- Python **3.12+**
- `libxkbcommon`
- A typing tool: `wtype` on Wayland, `xdotool` on X11, or `ydotool` on either
  (`ydotool` needs the `ydotoold` daemon running)
- User must be in the `input` group: `sudo usermod -aG input $USER` (then log out / in)

`setup.sh` installs all of this for you on any distribution it recognises.

### Wayland notes

Wayland has no protocol for reading the keyboard globally, so frfix reads
`/dev/input` directly through evdev instead — that works the same on both
display servers, and is why the `input` group is required.

Injection uses the `virtual-keyboard` protocol via `wtype`, which Hyprland,
Sway, and other wlroots compositors support. GNOME and KDE do not implement
that protocol; on those, install `ydotool` and run `ydotoold`.

## Troubleshooting

- **`PermissionError` opening `/dev/input/event*`** — you're not in the `input` group, or you haven't logged out and back in since being added.
- **Nothing gets corrected** — check `frfix --debug`. If keystrokes don't print, evdev access is broken. If words print but corrections don't fire, hunspell isn't installed or the layout isn't `fr`.
- **Corrections fire but garble the word** — injection timing. Try running outside a terminal multiplexer, or switch backend (install `ydotool`).
- **Nothing corrected in most windows, but it works in some** — the `xdotool` backend was picked on a Wayland session, so only XWayland windows receive the keystrokes. Install `wtype`. The startup banner names the backend in use.
- **`ImportError: The Grammalecte engine is missing`** — run `.venv/bin/frfix-bootstrap`. It downloads the engine from grammalecte.net, so it needs network access.
- **Wrong characters being typed** — keysym translation is using the wrong layout. Check the banner's `active layout` line, or pass `--force-layout fr`.
- **The service starts but does nothing** — check `journalctl --user -u frfix`. If the banner says `layout backend : none`, frfix could not talk to your compositor; run `--no-layout-check` to correct unconditionally.

## Project layout

```
frfix/
├── frfix/
│   ├── daemon.py      # asyncio event loop, layout monitor
│   ├── capture.py     # evdev → KeyAction events
│   ├── xchar.py       # xkbcommon keycode → char
│   ├── layout.py      # layout detection + switching per desktop
│   ├── buffer.py      # word + sentence state machine
│   ├── corrector.py   # grammalecte spelling + grammar
│   ├── injector.py    # wtype / xdotool / ydotool synthesis
│   ├── bootstrap.py   # one-time Grammalecte engine download
│   ├── overlay.py     # optional GTK toast (not wired in yet)
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
