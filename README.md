# frfix

System-wide real-time French autocorrect daemon for Linux/X11.

Runs in the background, captures keystrokes via evdev, and silently corrects French text as you type in any application.

## What it corrects

- **Accents**: `francais` → `français`, `realite` → `réalité`, `ecran` → `écran`
- **Elisions**: `cest` → `c'est`, `jai` → `j'ai`, `lhomme` → `l'homme`, `cetait` → `c'était`
- **Typos**: `vrqi` → `vrai`, `fqire` → `faire`, `voulqis` → `voulais`
- **Grammar** (at sentence boundaries): `tu peut` → `tu peux`, `je veut` → `je veux`

Conservative by design — never touches valid French words.

## How it works

- **evdev** captures physical keystrokes system-wide (read-only, no grab)
- **X11 keysym tables** translate keycodes to characters based on active layout
- **grammalecte** provides spelling suggestions and grammar checking
- **xdotool** injects corrections (backspace + retype)
- Only active when keyboard layout is `fr` — pauses on other layouts
- Switches to `fr` on start, restores previous layout on exit

## Install

```bash
git clone https://github.com/lemmebee/frfix.git
cd frfix
bash setup.sh
```

## Run

```bash
# manual
.venv/bin/frfix

# with debug output
.venv/bin/frfix --debug

# as systemd user service
systemctl --user enable --now frfix
```

Or use the Makefile:

```bash
make run      # install + run
make debug    # install + run with debug output
```

## Config

Config file: `~/.config/frfix/frfix.toml`

Custom dictionary: `~/.config/frfix/dictionary.txt` (one word per line)

## Requirements

- Linux with X11
- Python 3.12+
- `xdotool`
- User must be in the `input` group (`sudo usermod -aG input $USER`)
