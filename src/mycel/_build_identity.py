"""Read the immutable package-local Build number supplied by offline staging."""

from importlib.resources import files
import json
import sys

from ._errors import MycelError


def current_build() -> int | None:
    """Explicit source development returns None; damaged packages fail closed."""
    package = files("mycel")
    source = package.joinpath("data/build-identity.json")
    try:
        raw = source.read_bytes()
    except FileNotFoundError:
        # Staging excludes this exact source-development marker. Absence in a
        # numbered package must never downgrade an audited mutation to source
        # development. Installed runners use -I and cannot accept the marker.
        try:
            marker = package.joinpath("data/development-identity.json").read_bytes()
        except OSError:
            marker = None
        if marker == b'{"schemaVersion":1,"development":true}\n' and not sys.flags.isolated:
            return None
        raise MycelError("internal", "The installed Build identity is missing.") from None
    except OSError:
        raise MycelError("internal", "The installed Build identity could not be read.") from None
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != {"schemaVersion", "build"}
                or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
                or type(value["build"]) is not int or value["build"] <= 0):
            raise ValueError("identity")
        return value["build"]
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise MycelError("internal", "The installed Build identity is damaged.") from None
