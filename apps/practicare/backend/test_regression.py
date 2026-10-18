"""Compatibility entry point for the isolated authenticated regression suite.

The previous script targeted a live localhost service and the configured database.
This entry point intentionally delegates to disposable in-process fixtures instead.
"""

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[3] / "tests"
sys.path.insert(0, str(TESTS_DIR))

from test_practicare_crud import PractiCareCrudIntegrationTests
from test_verified_execution_and_rbac import PractiCareAuthorizationIntegrationTests


def run_all_tests():
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PractiCareCrudIntegrationTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PractiCareAuthorizationIntegrationTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    run_all_tests()
