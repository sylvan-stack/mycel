"""Installed module entry point for the isolated bundled interpreter."""

from ._cli import main


if __name__ == "__main__":
    raise SystemExit(main())
