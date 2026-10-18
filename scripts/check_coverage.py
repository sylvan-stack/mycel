#!/usr/bin/env python3
"""Run the automatic checks and emit the complete requirement proof report."""

from run_checks import main


if __name__ == "__main__":
    raise SystemExit(main(json_output=True))
