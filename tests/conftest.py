import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(scope="session")
def run_mode():
    """Local execution of our own trusted samples."""
    return {"allow_local": True}
