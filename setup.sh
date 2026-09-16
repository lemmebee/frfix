#!/usr/bin/env bash
# frfix setup. Works on any Linux distribution and on both X11 and Wayland:
# the package names are resolved per package manager, and the injection tool is
# chosen from the session type rather than assumed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
UNIT_DIR="$HOME/.config/systemd/user"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32m+\033[0m %s\n' "$*"; }

# --- 1. work out the package manager -----------------------------------

detect_pm() {
    for pm in pacman apt-get dnf zypper apk xbps-install emerge; do
        if command -v "$pm" >/dev/null 2>&1; then
            echo "$pm"
            return 0
        fi
    done
    return 1
}

# Package names differ per distro. Columns: python headers, compiler,
# libxkbcommon, Wayland typing tool, X11 typing tool.
packages_for() {
    case "$1" in
        pacman)       echo "python gcc libxkbcommon wtype xdotool" ;;
        apt-get)      echo "python3-dev python3-venv build-essential libxkbcommon0 wtype xdotool" ;;
        dnf)          echo "python3-devel gcc libxkbcommon wtype xdotool" ;;
        zypper)       echo "python3-devel gcc libxkbcommon0 wtype xdotool" ;;
        apk)          echo "python3-dev build-base libxkbcommon wtype xdotool" ;;
        xbps-install) echo "python3-devel gcc libxkbcommon wtype xdotool" ;;
        emerge)       echo "dev-lang/python x11-libs/libxkbcommon gui-apps/wtype x11-misc/xdotool" ;;
    esac
}

install_cmd() {
    case "$1" in
        pacman)       echo "sudo pacman -S --needed --noconfirm" ;;
        apt-get)      echo "sudo apt-get install -y" ;;
        dnf)          echo "sudo dnf install -y" ;;
        zypper)       echo "sudo zypper install -y" ;;
        apk)          echo "sudo apk add" ;;
        xbps-install) echo "sudo xbps-install -Sy" ;;
        emerge)       echo "sudo emerge --noreplace" ;;
    esac
}

say "[1/6] System packages"
if PM="$(detect_pm)"; then
    PKGS="$(packages_for "$PM")"
    CMD="$(install_cmd "$PM")"
    echo "  package manager: $PM"
    echo "  installing: $PKGS"
    # A single unavailable package must not abort the whole run; the checks at
    # the end report anything that is actually still missing.
    if ! $CMD $PKGS; then
        warn "some packages failed to install; continuing and checking below"
    fi
else
    warn "no known package manager found. Install these manually:"
    warn "  python3 headers, a C compiler, libxkbcommon, and wtype (Wayland) or xdotool (X11)"
fi

say "[2/6] Input device access"
# evdev reads /dev/input/event*, which is restricted to the 'input' group.
if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
    ok "$USER is already in the 'input' group"
else
    sudo usermod -aG input "$USER"
    warn "added $USER to the 'input' group. Log out and back in before starting frfix."
fi

say "[3/6] Python virtualenv"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -e "$REPO_DIR" --quiet
ok "installed into $VENV_DIR"

say "[4/6] Grammalecte engine"
# The 'grammalecte' module is not on PyPI; pygrammalecte downloads it on first
# use. Do that now so the daemon does not fail on its first launch.
"$VENV_DIR/bin/frfix-bootstrap"

say "[5/6] Checking the session"
SESSION="${XDG_SESSION_TYPE:-unknown}"
echo "  session type: $SESSION"
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    if command -v wtype >/dev/null 2>&1; then
        ok "Wayland session, wtype available"
    else
        warn "Wayland session but wtype is missing. Corrections will only reach"
        warn "XWayland windows. Install wtype, or ydotool with ydotoold running."
    fi
elif [ -n "${DISPLAY:-}" ]; then
    command -v xdotool >/dev/null 2>&1 \
        && ok "X11 session, xdotool available" \
        || warn "X11 session but xdotool is missing; install it"
else
    warn "no graphical session detected; run setup from inside your desktop session"
fi

say "[6/6] systemd user service"
mkdir -p "$UNIT_DIR"
sed "s|@FRFIX_BIN@|$VENV_DIR/bin/frfix|" \
    "$REPO_DIR/systemd/frfix.service" > "$UNIT_DIR/frfix.service"
systemctl --user daemon-reload
ok "installed $UNIT_DIR/frfix.service"

# graphical-session.target is only reached if the compositor tells systemd
# about it. Warn rather than fail, since the service still starts manually.
if ! systemctl --user is-active --quiet graphical-session.target; then
    warn "graphical-session.target is not active, so the service will not"
    warn "autostart. Either start it from your compositor config, or run:"
    warn "  systemctl --user add-wants default.target frfix.service"
fi

say "Setup complete"
cat <<MSG
  Start now:          systemctl --user start frfix
  Start with session: systemctl --user enable frfix
  Follow the log:     journalctl --user -u frfix -f
  Run in foreground:  $VENV_DIR/bin/frfix --debug
MSG
