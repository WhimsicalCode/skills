import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "tech-tree" / "scripts"
SCRIPT = SCRIPTS / "techtree.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def run_script(*args, cwd, check=True):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd, capture_output=True,
                          text=True, check=check)


def write_tree(folder, tasks, edges=(), groups=None):
    """A tree.json from a compact description: tasks as {id: status} or {id: (status, title)}."""
    spec = {}
    for t, value in tasks.items():
        status, title = value if isinstance(value, tuple) else (value, f"Task {t}")
        spec[t] = {"title": title, "status": status}
    path = Path(folder) / "tree.json"
    path.write_text(json.dumps({"tasks": spec, "groups": groups or {}, "edges": [list(e) for e in edges]}))
    return path


@pytest.fixture(scope="session")
def plans():
    """Each fixture tree laid out once for the whole session: it takes a few seconds."""
    import techtree
    return {name: techtree.layout(FIXTURES / f"{name}.json") for name in ("carbonara", "analytics", "offsite")}
