"""Check current keyboard layout — only correct when layout is French."""

import subprocess


def is_french_layout() -> bool:
    """Return True if the current active keyboard layout is French."""
    # Method 1: GNOME gsettings (most reliable for GNOME/Ubuntu)
    try:
        # Get current index
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "current"],
            capture_output=True, text=True, timeout=1,
        )
        current_idx = int(result.stdout.strip().split()[-1])

        # Get sources list
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
            capture_output=True, text=True, timeout=1,
        )
        # Parse: [('xkb', 'gb'), ('xkb', 'ara'), ('xkb', 'fr')]
        sources_str = result.stdout.strip()
        layouts = []
        for part in sources_str.split("'"):
            # Every other quoted string after 'xkb' is the layout name
            if len(part) <= 5 and part.isalpha() and part != "xkb":
                layouts.append(part)

        if current_idx < len(layouts):
            return layouts[current_idx] == "fr"
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass

    # Method 2: fallback to setxkbmap (single layout or first layout)
    try:
        result = subprocess.run(
            ["setxkbmap", "-query"],
            capture_output=True, text=True, timeout=1,
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("layout:"):
                layouts = line.split(":", 1)[1].strip()
                first = layouts.split(",")[0].strip()
                return first == "fr"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False
