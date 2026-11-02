"""Entry point for ``python -m naji`` and the ``naji`` script."""

from __future__ import annotations


def main() -> int:
    from naji.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
