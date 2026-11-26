import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def trial():
    """dev/try.py as a module. `try` is a keyword, so it can't be imported by name."""
    spec = importlib.util.spec_from_file_location("trial", ROOT / "dev" / "try.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
