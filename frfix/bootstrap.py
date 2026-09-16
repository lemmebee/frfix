"""Fetch the Grammalecte engine that the corrector imports.

The `grammalecte` module is not published on PyPI. `pygrammalecte` downloads
and installs it (as the `Grammalecte-fr` distribution) the first time it runs,
so a plain `pip install` leaves the engine missing until something triggers
that. This module makes the step explicit so setup can do it up front instead
of the daemon failing on first launch.

Run as `frfix-bootstrap`, or `python -m frfix.bootstrap`.
"""

import sys


def main() -> int:
    try:
        import grammalecte  # noqa: F401
        print("frfix: Grammalecte engine already present.")
        return 0
    except ImportError:
        pass

    try:
        from pygrammalecte import grammalecte_text
    except ImportError:
        print(
            "frfix: pygrammalecte is not installed. Run 'pip install -e .' first.",
            file=sys.stderr,
        )
        return 1

    print("frfix: downloading the Grammalecte French engine (one time)...")
    try:
        list(grammalecte_text("Ceci est un test."))  # the call performs the install
        import grammalecte  # noqa: F401
    except Exception as exc:
        print(
            f"frfix: could not install the Grammalecte engine: {exc}\n"
            "       It is downloaded from grammalecte.net, so check network "
            "access and retry.",
            file=sys.stderr,
        )
        return 1

    print("frfix: Grammalecte engine installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
