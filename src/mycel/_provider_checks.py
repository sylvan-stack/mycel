# Test implementations moved to tests/mid/archived/src/mycel/_provider_checks.py.
"""Explicit genuine on-demand operations, kept outside automatic discovery.

No serialized report is accepted as a proof. The caller retains the returned
live OnDemandProofs object in this process for the exact immutable Build.
Component profile reports remain separately reviewable provenance.
"""
from __future__ import annotations

import unittest

from ._coverage import run_on_demand_checks
from ._errors import MycelError


def run_provider_checks(settings, suite, *, repository, build, implementation_identity,
                        live=False):
    return _mid_tier_namespace()['run_provider_checks'](settings, suite, repository=repository, build=build, implementation_identity=implementation_identity, live=live)


def _mid_tier_namespace():
    """Load test-only code on explicit invocation, leaving normal product imports alone."""
    from pathlib import Path as _TierPath
    from types import ModuleType as _TierModule
    import sys as _tier_sys
    name = __name__ + '.__mid_tier'
    if name not in _tier_sys.modules:
        path = _TierPath(__file__).resolve().parents[2] / 'tests/mid/archived/src/mycel/_provider_checks.py'
        if not path.is_file():
            raise RuntimeError('Mid-tier source is unavailable in this installation; use the source checkout or an explicitly qualified test package. See MID_TIER.md.')
        module = _TierModule(name)
        # Preserve public case identities consumed by qualification contracts.
        module.__dict__['__name__'] = __name__
        module.__file__ = __file__
        module.__package__ = __package__
        _tier_sys.modules[name] = module
        try:
            exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        except BaseException:
            del _tier_sys.modules[name]
            raise
    return _tier_sys.modules[name].__dict__
