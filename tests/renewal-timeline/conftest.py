import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "renewal-timeline"
SCRIPTS = SKILL / "scripts"
SCRIPT = SCRIPTS / "build_board.py"
EXAMPLE = SKILL / "examples" / "events.example.json"
# A real fetch(detail: "detailed") of the board the example draws (fictional data).
BOARD = Path(__file__).resolve().parent / "fixtures" / "example-board.json"
sys.path.insert(0, str(SCRIPTS))


def run_script(*args, check=True):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, check=check)


def example():
    """A fresh copy of the example events.json, to change in a test."""
    return json.loads(EXAMPLE.read_text())


def write(tmp_path, data, name="events.json"):
    f = tmp_path / name
    f.write_text(json.dumps(data))
    return f
