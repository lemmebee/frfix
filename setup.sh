#!/bin/bash
set -e

echo "=== frfix setup ==="

# 1. System dependencies
echo "[1/5] Installing system packages..."
sudo apt-get install -y \
    libhunspell-dev \
    hunspell-fr-comprehensive \
    python3-dev \
    python3-venv \
    libgirepository1.0-dev \
    gir1.2-gtk-3.0 \
    at-spi2-core \
    gir1.2-atspi-2.0 \
    x11-xkb-utils

# 2. Add user to input group (for evdev access)
echo "[2/5] Adding $USER to input group..."
if ! groups "$USER" | grep -q '\binput\b'; then
    sudo usermod -aG input "$USER"
    echo "  Added to input group. You'll need to log out and back in for this to take effect."
else
    echo "  Already in input group."
fi

# 3. Python venv + dependencies
echo "[3/5] Setting up Python venv..."
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

# 4. Try installing grammalecte (optional)
echo "[4/5] Installing grammalecte (optional, for grammar checking)..."
.venv/bin/pip install grammalecte 2>/dev/null || echo "  grammalecte not available on pip — grammar checking will be spelling-only"

# 5. Install systemd user service
echo "[5/5] Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cp systemd/frfix.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
echo "  Service installed. Start with: systemctl --user start frfix"
echo "  Auto-start on login:           systemctl --user enable frfix"

echo ""
echo "=== Setup complete ==="
echo ""
echo "To run manually:  cd $(pwd) && .venv/bin/frfix"
echo "To run as service: systemctl --user enable --now frfix"
echo ""
echo "NOTE: If you just got added to the 'input' group, log out and back in first."
