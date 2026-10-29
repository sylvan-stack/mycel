# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Executed checks for the automatic gate machinery and on-demand checks."""

from __future__ import annotations

import os
import tomllib
import unittest

import psycopg

_CAPTURED_CONNECT = psycopg.connect
_CAPTURED_CLASS_CONNECT = psycopg.Connection.connect
_CAPTURED_ASYNC_CONNECT = psycopg.AsyncConnection.connect


def example_check(*, name="Example", kind="unit", action=None, skip=False):
    def runTest(self):
        if skip:
            self.skipTest("deliberately not executed")
        if action:
            action(self)
    return type(name, (unittest.TestCase,), {"runTest": runTest, "check_kind": kind})()


class SimulatedBackend:
    real_store = False

    def __init__(self, *, fail_init=False, fail_drop=False):
        self.events = []
        self.fail_init = fail_init
        self.fail_drop = fail_drop

    def address(self, database):
        return "postgresql://localhost/" + database

    def create_database(self, database):
        self.events.append(("create", database))

    def initialize(self, settings_file):
        self.events.append(("initialize", settings_file))
        data = tomllib.loads(settings_file.read_text())
        if set(data) != {"store"} or set(data["store"]) != {"address"}:
            raise AssertionError("copied owner settings")
        if os.environ.get("MYCEL_CONFIG") != str(settings_file):
            raise AssertionError("test did not own MYCEL_CONFIG")
        if self.fail_init:
            raise RuntimeError("initialization failed")

    def drop_database(self, database):
        self.events.append(("drop", database))
        if self.fail_drop:
            raise RuntimeError("cleanup failed")


class CoverageTests(unittest.TestCase):
    pass  # TEST-TIER-EMPTY-SUITE; helpers remain importable.



# Archived complete imports; restore needed names in their original scope, not at this file tail.
