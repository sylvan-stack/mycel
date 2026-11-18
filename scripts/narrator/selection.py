"""Checkout entry point for the bundled Narrator selection."""

from importlib import import_module
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
_implementation = import_module("mycel._narrator.selection")


def __getattr__(name: str):
    return getattr(_implementation, name)
