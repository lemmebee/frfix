"""Fetch the Grammalecte engine that the corrector imports.

The `grammalecte` module is not published on PyPI. `pygrammalecte` downloads
and installs it (as the `Grammalecte-fr` distribution) the first time it runs,
so a plain `pip install` leaves the engine missing until something triggers
that. This module makes the step explicit so setup can do it up front instead
of the daemon failing on first launch.

Run as `frfix-bootstrap`, or `python -m frfix.bootstrap`.
"""

import sys


def engine_available() -> bool:
    try:
        import grammalecte  # noqa: F401
    except ImportError:
        return False
    return True


def install_engine() -> bool:
    """Trigger pygrammalecte's one-time download of the Grammalecte engine."""
    try:
        from pygrammalecte import grammalecte_text
    except ImportError:
        print(
            "frfix: pygrammalecte is not installed. Run 'pip install -e .' first.",
            file=sys.stderr,
        )
        return False

    print("frfix: downloading the Grammalecte French engine (one time)...")
    try:
        # The call itself is what performs the install; the result is unused.
        list(grammalecte_text("Ceci est un test."))
    except Exception as exc:
        print(f"frfix: could not install the Grammalecte engine: {exc}", file=sys.stderr)
        return False
    return engine_available()


def main() -> int:
    if engine_available():
        print("frfix: Grammalecte engine already present.")
        return 0
    if install_engine():
        print("frfix: Grammalecte engine installed.")
        return 0
    print(
        "frfix: the Grammalecte engine is still missing. It is downloaded from\n"
        "       grammalecte.net, so check network access and retry.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
