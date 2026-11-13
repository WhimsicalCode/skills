"""Try a skill the way a user would: install it into a new, empty folder and start an agent there.

    uv run dev/try.py <skill> [--agent claude|codex|none] [--source PATH_OR_REPO] [--prompt TEXT] [FILE ...]

The skill is installed with the same `npx skills add` command as the guides, from this working copy
unless --source says otherwise. To try what's published, name it WhimsicalCode/skills/<skill>. The agent
only gets the MCP servers listed in the skill's marketplace.json entry, and Claude Code skips your
user settings, so your own plugins stay out of the way. FILEs are copied into the folder, to give the
agent something to work on. Runs go in ~/skill-bench, or $SKILL_BENCH.

With --prompt, the agent runs on its own with that request, as a user would type it, and the script
reports what it answered, how long it took and what it wasn't allowed to do. It may edit files in
the folder, run python3 and the commands below, and call the skill's MCP servers; anything else is
refused rather than waited for. MCP servers it isn't signed in to don't work in these runs.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(os.environ.get("SKILL_BENCH", Path.home() / "skill-bench"))
AGENTS = {"claude": "claude-code", "codex": "codex"}
# What a run with --prompt may do without asking, in Claude Code's terms.
ALLOWED = ["Read", "Write", "Edit", "Skill", "Task", "Agent", "Bash(python3:*)", "Bash(uv run:*)", "Bash(cd:*)",
           "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)", "Bash(cp:*)"]


def fail(message):
    sys.exit(f"try: {message}")


def mcp_servers(skill):
    plugins = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())["plugins"]
    entry = next((p for p in plugins if p["name"] == skill), None)
    if entry is None:
        fail(f"{skill} has no entry in .claude-plugin/marketplace.json; add one first (see CONTRIBUTING.md)")
    servers = entry.get("mcpServers", {})
    for name, server in servers.items():
        if server.get("type") != "http":
            fail(f"MCP server {name} isn't an http server; dev/try.py only knows how to set those up")
    return servers


def launch_command(agent, servers):
    if agent == "claude":
        return ["claude", "--strict-mcp-config", "--mcp-config", ".mcp.json", "--setting-sources", "project,local"]
    return ["codex", *codex_config(servers)]


def codex_config(servers):
    return [arg for name, server in servers.items() for arg in ["-c", f'mcp_servers.{name}.url="{server["url"]}"']]


def run_headless(agent, servers, prompt, run):
    """Run the agent on its own with the prompt; save everything it printed in the run folder."""
    if agent == "claude":
        allowed = " ".join(ALLOWED + [f"mcp__{name}" for name in servers])
        command = [*launch_command(agent, servers), "-p", prompt, "--output-format", "json",
                   "--permission-mode", "acceptEdits", "--allowedTools", allowed]
    else:
        command = ["codex", "exec", "--full-auto", "--skip-git-repo-check", *codex_config(servers), prompt]
    print(f"\nRunning {agent} on its own in {run}. This takes a few minutes.", flush=True)
    started = time.monotonic()
    result = subprocess.run(command, cwd=run, capture_output=True, text=True, check=False)
    minutes = (time.monotonic() - started) / 60
    (run / "run.log").write_text(result.stdout + result.stderr)
    if agent == "claude":
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            fail(f"claude didn't finish normally (exit {result.returncode}); see {run / 'run.log'}")
        print(f"\n{report.get('result', '')}\n")
        refused = report.get("permission_denials") or []
        print(f"{minutes:.1f} minutes, {report.get('num_turns')} turns, ${report.get('total_cost_usd', 0):.2f}")
        for denial in refused:
            print(f"  refused: {denial.get('tool_name')} {json.dumps(denial.get('tool_input'))[:150]}")
    else:
        print("\n" + "\n".join(result.stdout.splitlines()[-40:]))
        print(f"\n{minutes:.1f} minutes, exit {result.returncode}")
    print(f"Everything it printed: {run / 'run.log'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("skill")
    parser.add_argument("--agent", choices=[*AGENTS, "none"], default="claude", help="agent to start (default claude)")
    parser.add_argument("--source", default=str(ROOT), help="where to install from (default this working copy)")
    parser.add_argument("--prompt", help="run the agent on its own with this request, and report how it went")
    parser.add_argument("files", nargs="*", type=Path, help="files to copy into the folder")
    args = parser.parse_args()
    if args.prompt and args.agent == "none":
        fail("--prompt needs an agent: --agent claude or --agent codex")
    if "/" in args.skill:
        args.source, _, args.skill = args.skill.rpartition("/")

    servers = mcp_servers(args.skill)
    for tool in ["npx", *([] if args.agent == "none" else [args.agent])]:
        if not shutil.which(tool):
            fail(f"{tool} isn't installed")
    for file in args.files:
        if not file.is_file():
            fail(f"{file} isn't a file")

    run = BENCH / f"{args.skill}-{datetime.now():%Y%m%d-%H%M%S}"
    run.mkdir(parents=True)
    install = ["npx", "-y", "skills@latest", "add", args.source, "--skill", args.skill,
               "--agent", *AGENTS.values(), "-y"]
    print("$", shlex.join(install), flush=True)
    subprocess.run(install, cwd=run, check=False)
    # The installer can skip a skill, for example when its frontmatter isn't valid YAML, and still exit 0.
    for folder in [".claude/skills", ".agents/skills"]:
        if not (run / folder / args.skill / "SKILL.md").exists():
            shutil.rmtree(run)
            fail(f"the installer didn't install {args.skill} for every agent; read its output above")

    (run / ".mcp.json").write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n")
    for file in args.files:
        shutil.copy2(file, run)

    if args.prompt:
        run_headless(args.agent, servers, args.prompt, run)
        return

    print(f"\nReady in {run}")
    print("MCP servers:", ", ".join(servers) or "none")
    print("Start an agent there with:")
    for agent in AGENTS:
        print(f"  {agent}: cd {run} && {shlex.join(launch_command(agent, servers))}")
    print("Sign in to the MCP servers with /mcp in Claude Code. In Codex, sign in before starting it:")
    for name in servers:
        print(f"  {shlex.join(['codex', 'mcp', 'login', name, *codex_config(servers)])}")
    if args.agent != "none":
        os.chdir(run)
        os.execvp(args.agent, launch_command(args.agent, servers))


if __name__ == "__main__":
    main()
