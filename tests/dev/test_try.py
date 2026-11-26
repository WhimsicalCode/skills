import json

import pytest
from conftest import ROOT

SKILLS = [p["name"] for p in json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())["plugins"]]


@pytest.mark.parametrize("skill", SKILLS)
def test_every_guide_has_install_steps_fresh_runs_can_follow(trial, skill):
    commands = trial.guide_install(skill, trial.PUBLISHED)
    installs = [c for c in commands if c[:3] == ["npx", "skills", "add"]]
    assert installs, f"docs/{skill}.md's Claude Code tab installs the skill with npx skills add"
    assert installs[0][3] == "WhimsicalCode/skills" and skill in installs[0]
    added = {c[-2] for c in commands if c[:3] == ["claude", "mcp", "add"]}   # ... <name> <url>
    servers = trial.mcp_servers(skill)
    assert set(servers) <= added, f"docs/{skill}.md adds every MCP server its plugin entry lists"


def test_the_working_copy_replaces_the_published_repository(trial):
    commands = trial.guide_install("tech-tree", "/work/skills")
    install = next(c for c in commands if c[:3] == ["npx", "skills", "add"])
    assert install[3] == "/work/skills"
    assert all("WhimsicalCode/skills" not in c for c in commands if c[:3] == ["npx", "skills", "add"])
    mcp = [c for c in commands if c[:2] == ["claude", "mcp"]]
    assert [c[-1] for c in mcp if "whimsical" in c] == ["https://mcp.whimsical.com/mcp"]


def test_keychain_service_is_named_as_claude_code_names_it(trial):
    # Checked on a Mac: Claude Code kept /tmp/fresh-claude-test/config's sign-ins under this name.
    assert trial.keychain_service("/tmp/fresh-claude-test/config") == "Claude Code-credentials-efe25bed"


def test_a_guide_without_a_claude_code_block_fails_clearly(trial, tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "acme.md").write_text("# Acme\n\n## Install\n\n### Cursor\n\n```sh\nnpx skills add x\n```\n")
    monkeypatch.setattr(trial, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="no ```sh block under ## Install > ### Claude Code"):
        trial.guide_install("acme", trial.PUBLISHED)


def test_fresh_needs_claude_code(trial, monkeypatch):
    monkeypatch.setattr("sys.argv", ["try.py", "tech-tree", "--fresh", "--agent", "codex"])
    with pytest.raises(SystemExit, match="--fresh works with --agent claude"):
        trial.main()


def test_in_terminal_runs_a_command_as_if_typed_in_one(trial, tmp_path):
    seen = []
    code, text = trial.in_terminal(["python3", "-c", "import sys; print(sys.stdout.isatty()); print('x' * 300)"],
                                   None, tmp_path, wait=30, show=seen.append)
    assert code == 0
    assert seen[0] == "True", "the command sees a terminal, so sign-in commands open the browser"
    assert "x" * 300 in text, "long lines aren't wrapped"


def test_tokens_are_recognised_to_be_hidden(trial):
    line = "Your OAuth token: sk-ant-oat01-" + "Ab3_-" * 20
    assert trial.TOKEN.sub("[token]", line) == "Your OAuth token: [token]"


def test_in_terminal_waits_for_a_command_that_exits_after_closing_its_terminal(trial, tmp_path):
    # As claude mcp login does once authorized: the terminal closes, then the process exits.
    script = "import os, time; print('Authenticated'); os.close(0); os.close(1); os.close(2); time.sleep(1)"
    code, text = trial.in_terminal(["python3", "-c", script], None, tmp_path, wait=30)
    assert code == 0 and "Authenticated" in text


def test_a_token_is_read_without_the_line_after_it(trial):
    screen = "Your OAuth token (valid for 1 year):\r\nsk-ant-oat01-" + "Ab3_" * 20 + "\r\nStorethistokensecurely."
    assert trial.TOKEN.search(screen.replace("\r", "\n"))[0] == "sk-ant-oat01-" + "Ab3_" * 20
