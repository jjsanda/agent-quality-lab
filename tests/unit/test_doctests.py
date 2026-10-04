"""Run the doctests embedded in the load-bearing modules as part of the suite.

The list grows as new doctested modules are added; keeping it explicit (rather than auto-
discovering everything) avoids importing modules with heavy optional dependencies.
"""

from __future__ import annotations

import doctest
import importlib

import pytest

DOCTEST_MODULES = [
    "aql.domain.incidents",
    "aql.domain.tools_schema",
    "aql.domain.policy",
    "aql.domain.evidence",
    "aql.adapters.tools.registry",
    "aql.config.settings",
    "aql.factory",
]


@pytest.mark.parametrize("module_name", DOCTEST_MODULES)
def test_module_doctests(module_name: str) -> None:
    module = importlib.import_module(module_name)
    results = doctest.testmod(module, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed in {module_name}"
