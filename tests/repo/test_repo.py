"""Checks that every skill follows the repository's conventions and is listed everywhere it should be.
They run over every folder in skills/, so a new skill is covered without new tests.
"""
import ast
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
MARKETPLACE = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
FRONTMATTER_KEYS = {"name", "description", "license", "metadata", "allowed-tools"}
COVERS = ROOT / "docs" / "covers"
COVER_KEYS = {"category", "headline"}
# Distribution names whose import name differs.
IMPORT_NAMES = {"pillow": "PIL"}


def frontmatter(skill):
    text = (skill / "SKILL.md").read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{skill.name}: SKILL.md needs YAML frontmatter"
    # Plain `key: value` lines are all the frontmatter needs; no YAML parser required.
    return dict(line.split(": ", 1) for line in match[1].splitlines() if not line.startswith(" "))


def entry(skill):
    entries = [p for p in MARKETPLACE["plugins"] if p["name"] == skill.name]
    assert len(entries) == 1, f"{skill.name}: needs exactly one entry in .claude-plugin/marketplace.json"
    return entries[0]


def published_text_files():
    """Text files under skills/ and docs/ and the root Markdown files, as git tracks or would add them."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard",
                          "skills", "docs", ":(glob)*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.splitlines()
            if Path(f).suffix in {".md", ".py", ".json", ".txt"} and (ROOT / f).is_file()]


def test_skills_folder_is_not_empty():
    assert SKILLS


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_frontmatter(skill):
    meta = frontmatter(skill)
    assert set(meta) <= FRONTMATTER_KEYS, f"unexpected keys: {set(meta) - FRONTMATTER_KEYS}"
    assert meta["name"] == skill.name, "the folder name must match the skill's name"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
    assert 50 < len(meta["description"]) <= 1024
    assert not re.search(r"[<>]", meta["description"]), "Claude's skill upload rejects < and > in descriptions"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_body_under_500_lines(skill):
    assert len((skill / "SKILL.md").read_text().splitlines()) < 500


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_referenced_files_exist(skill):
    for doc in [skill / "SKILL.md", *skill.glob("references/*.md")]:
        text = doc.read_text()
        # `references/x.md`, <this skill's folder>/scripts/x.py, and relative Markdown links.
        refs = re.findall(r"(?:`|folder>/)((?:references|scripts|examples|assets)/[\w.-]+(?:/[\w.-]+)*)", text)
        refs += [link for link in re.findall(r"\]\(([^)#\s]+)", text) if "://" not in link]
        refs = [ref.rstrip(".") for ref in refs]
        for ref in refs:
            assert (skill / ref).exists() or (doc.parent / ref).exists(), f"{doc.relative_to(ROOT)}: missing {ref}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_listed_in_marketplace(skill):
    plugin = entry(skill)
    assert plugin["source"] == "./" and plugin["strict"] is False
    assert plugin["skills"] == [f"./skills/{skill.name}"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"])
    assert plugin["mcpServers"]["whimsical"]["url"] == "https://mcp.whimsical.com/mcp"


def test_marketplace_lists_only_skills_that_exist():
    names = [p["name"] for p in MARKETPLACE["plugins"]]
    assert sorted(names) == sorted(s.name for s in SKILLS)


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_has_guide_tests_and_gallery_row(skill):
    assert (ROOT / "docs" / f"{skill.name}.md").is_file(), f"add docs/{skill.name}.md"
    assert any((ROOT / "tests" / skill.name).glob("test_*.py")), f"add tests in tests/{skill.name}/"
    assert f"(docs/{skill.name}.md)" in (ROOT / "README.md").read_text(), "add a row to the README's skill table"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_guide_intro_is_what_the_website_shows(skill):
    # whimsical.com/skills reads the title and the intro, up to the first "##". See CONVENTIONS.md.
    guide = (ROOT / "docs" / f"{skill.name}.md").read_text()
    assert re.match(r"# \S.*\n\n", guide), "the guide starts with a '# Title' line, then a blank line"
    intro = guide.split("\n## ", 1)[0].split("\n", 1)[1].strip()
    first = intro.split("\n\n", 1)[0]
    assert not first.startswith(("```", "!", "[!", "|", "-")), "the intro opens with a paragraph of prose"
    assert re.search(r"^```text\n.+?\n```$", intro, re.S | re.M), "the intro has a ```text block with a prompt"
    install = re.search(r"^## Install\n(.*?)(?=^## |\Z)", guide, re.S | re.M)
    assert install, "the guide has an '## Install' section"
    tabs = re.findall(r"^### (.+)$", install[1], re.M)
    assert len(tabs) >= 2, "'## Install' has one '### ' subsection per agent"
    labels = [t.split(" (")[0] for t in tabs]
    assert all(len(label) <= 20 for label in labels), f"tab names, before ' (', stay short: {labels}"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_has_cover(skill):
    spec_path = COVERS / f"{skill.name}.json"
    assert spec_path.is_file(), f"add docs/covers/{skill.name}.json; see docs/covers/README.md"
    spec = json.loads(spec_path.read_text())
    assert set(spec) == COVER_KEYS, f"the cover spec has exactly {sorted(COVER_KEYS)}"
    assert all(isinstance(v, str) and v.strip() for v in spec.values())
    assert len(spec["headline"].split("\n")) <= 2, "the headline fits on two lines"

    art = COVERS / "art" / f"{skill.name}.svg"
    assert art.is_file(), f"draw docs/covers/art/{skill.name}.svg; see docs/covers/README.md"
    assert 'viewBox="0 0 720 520"' in art.read_text(), "the illustration's viewBox is 0 0 720 520"

    png = COVERS / f"{skill.name}.png"
    assert png.is_file(), f"render it: uv run docs/covers/render.py {skill.name}"
    header = png.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", header[16:24]) == (3200, 2000), \
        "the cover is rendered by docs/covers/render.py at 3200x2000"


def test_covers_only_for_skills_that_exist():
    names = {s.name for s in SKILLS}
    for path in [*COVERS.glob("*.json"), *COVERS.glob("*.png"), *(COVERS / "art").glob("*.svg")]:
        assert path.stem in names, f"{path.relative_to(ROOT)} belongs to no skill"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_scripts_import_only_the_standard_library_and_declared_packages(skill):
    for script in skill.glob("scripts/*.py"):
        source = script.read_text()
        block = re.search(r"^# /// script\n(.*?)^# ///$", source, re.S | re.M)
        declared = re.findall(r'"([A-Za-z0-9_.-]+)', re.search(r"dependencies = \[(.*?)\]", block[1])[1]) \
            if block else []
        allowed = set(sys.stdlib_module_names) | {p.stem for p in script.parent.glob("*.py")}
        allowed |= {IMPORT_NAMES.get(d.lower(), d.lower().replace("-", "_")) for d in declared}
        for node in ast.walk(ast.parse(source)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
            for name in names:
                assert name.split(".")[0] in allowed, f"{script.relative_to(ROOT)} imports {name}"


def test_no_em_dashes_in_published_text():
    for path in published_text_files():
        assert "\u2014" not in path.read_text(encoding="utf-8"), f"em-dash in {path.relative_to(ROOT)}"


def test_no_build_or_os_clutter_tracked():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert not re.search(r"(__pycache__|\.DS_Store|\.pyc$)", tracked, re.M)
