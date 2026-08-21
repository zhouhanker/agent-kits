"""Run the test suite and expose failures as GitHub Actions annotations."""

from __future__ import annotations

import sys
import unittest


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    for test, traceback in result.failures + result.errors:
        summary = traceback.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title={test.id()}::{summary}", file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
