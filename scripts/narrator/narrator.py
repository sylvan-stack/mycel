"""Checkout entry point for the bundled Narrator CLI."""

from importlib import import_module
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
_implementation = import_module("mycel._narrator.narrator")


def __getattr__(name: str):
    return getattr(_implementation, name)


if __name__ == "__main__":
    sys.exit(_implementation.main())
