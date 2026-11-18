#!/usr/bin/env python3
"""Render one opt-in Mycel maintenance LaunchAgent to standard output."""

import argparse
from hashlib import sha256
from pathlib import Path
import plistlib
import sys


def _absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path.")
    return value


def _repository(value: str) -> str:
    if not value or value.strip() != value or value.startswith("-"):
        raise argparse.ArgumentTypeError("Use one literal repository name.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, type=_absolute, help="installed Mycel launcher")
    parser.add_argument("--repo", required=True, type=_repository, help="one configured repository")
    parser.add_argument("--config", type=_absolute, help="optional settings file")
    options = parser.parse_args()

    identity = sha256(options.repo.encode("utf-8")).hexdigest()[:20]
    plist = {
        "Label": f"local.mycel.maintenance.{identity}",
        "ProgramArguments": [options.launcher, "maintain", "--repo", options.repo],
        "RunAtLoad": True,
        "StartInterval": 60,
    }
    if options.config:
        plist["EnvironmentVariables"] = {"MYCEL_CONFIG": options.config}
    plistlib.dump(plist, sys.stdout.buffer)


if __name__ == "__main__":
    main()
