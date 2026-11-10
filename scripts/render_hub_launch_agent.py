#!/usr/bin/env python3
"""Render the Mycel Hub and Cue Card LaunchAgent to standard output."""

import argparse
from pathlib import Path
import plistlib
import sys


def _absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, type=_absolute, help="installed Mycel launcher")
    parser.add_argument("--hub", required=True, type=_absolute, help="Instructions Hub source file")
    options = parser.parse_args()
    plist = {
        "Label": "local.mycel.hub-sync",
        "ProgramArguments": [options.launcher, "hub", "__sync"],
        "RunAtLoad": True,
        "StartInterval": 900,
        "WatchPaths": [options.hub],
    }
    plistlib.dump(plist, sys.stdout.buffer)


if __name__ == "__main__":
    main()
