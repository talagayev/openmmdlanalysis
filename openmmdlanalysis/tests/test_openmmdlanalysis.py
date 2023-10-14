"""
Unit and regression test for the openmmdlanalysis package.
"""

# Import package, test suite, and other packages as needed
import sys

import pytest

import openmmdlanalysis


def test_openmmdlanalysis_imported():
    """Sample test, will always pass so long as import statement worked."""
    assert "openmmdlanalysis" in sys.modules
