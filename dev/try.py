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

Those runs reuse your sign-ins, so they don't show what a new user goes through. --fresh does: it
starts Claude Code with a blank configuration (no MCP servers, connectors or sign-ins), runs the
Install > Claude Code commands from the skill's guide as they're written, opens the browser to
sign in to each MCP server (you click Authorize), runs the request, then deletes the sign-ins and
the configuration. Claude Code itself logs in with a token you save once:

    uv run dev/try.py --save-token
"""

import argparse
import fcntl
import getpass
import hashlib
import json
import os
import re
import select
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(os.environ.get("SKILL_BENCH", Path.home() / "skill-bench"))
AGENTS = {"claude": "claude-code", "codex": "codex"}
# What a run with --prompt may do without asking, in Claude Code's terms.
ALLOWED = ["Read", "Write", "Edit", "Skill", "Task", "Agent", "Bash(python3:*)", "Bash(uv run:*)", "Bash(cd:*)",
           "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)", "Bash(cp:*)"]


PUBLISHED = "WhimsicalCode/skills"
TOKEN_SERVICE = "whimsical-skills dev/try.py"   # where --save-token keeps the Claude token, in the Keychain
FRESH_STEPS = 5
TOKEN = re.compile(r"sk-ant-oat\w*-[\w-]{20,}")
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")


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


def run_headless(agent, servers, prompt, run, env=None):
    """Run the agent on its own with the prompt; save everything it printed in the run folder. With
    env, Claude Code runs with the MCP servers its configuration has (a --fresh run's)."""
    if agent == "claude":
        allowed = " ".join(ALLOWED + [f"mcp__{name}" for name in servers])
        start = ["claude"] if env else launch_command(agent, servers)
        command = [*start, "-p", prompt, "--output-format", "json",
                   "--permission-mode", "acceptEdits", "--allowedTools", allowed]
    else:
        # Codex on its own can't ask, so it cancels MCP calls that need approval: approve the skill's servers.
        approve = [arg for name in servers
                   for arg in ["-c", f'mcp_servers.{name}.default_tools_approval_mode="approve"']]
        command = ["codex", "exec", "--full-auto", "--skip-git-repo-check", *codex_config(servers), *approve, prompt]
    print(f"\nRunning {agent} on its own in {run}. This takes a few minutes.", flush=True)
    started = time.monotonic()
    result = subprocess.run(command, cwd=run, capture_output=True, text=True, check=False, env=env)
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


# --- --fresh: what a new user goes through ------------------------------------------------------

def guide_install(skill, source):
    """The commands the guide's Install > Claude Code tab tells a new user to run, with the skill
    installed from source instead of the published repository when they differ."""
    guide = ROOT / "docs" / f"{skill}.md"
    if not guide.is_file():
        fail(f"docs/{skill}.md is missing; --fresh follows the guide's install steps")
    install = re.search(r"^## Install\n(.*?)(?=^## |\Z)", guide.read_text(), re.S | re.M)
    tab = install and re.search(r"^### Claude Code\n(.*?)(?=^### |\Z)", install[1], re.S | re.M)
    block = tab and re.search(r"^```sh\n(.*?)^```", tab[1], re.S | re.M)
    if not block:
        fail(f"docs/{skill}.md has no ```sh block under ## Install > ### Claude Code")
    text = block[1].replace("\\\n", " ")
    commands = [shlex.split(line) for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if source != PUBLISHED:
        commands = [[source if word == PUBLISHED and "skills" in command[:3] else word for word in command]
                    for command in commands]
    return commands


def keychain_service(config):
    """The Keychain entry where Claude Code keeps a configuration's sign-ins, on a Mac. It's named
    after the configuration folder, as Claude Code names it."""
    return "Claude Code-credentials-" + hashlib.sha256(str(config).encode()).hexdigest()[:8]


def claude_token():
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not token and sys.platform == "darwin":
        found = subprocess.run(["security", "find-generic-password", "-s", TOKEN_SERVICE, "-w"],
                               capture_output=True, text=True, check=False)
        token = found.stdout.strip() if found.returncode == 0 else ""
    if not token:
        fail("--fresh logs in to Claude Code with a token. Save one first: uv run dev/try.py --save-token "
             "(or set CLAUDE_CODE_OAUTH_TOKEN)")
    return token


def save_token():
    """Make a long-lived Claude Code token and keep it in the Keychain, for --fresh runs. The
    browser opens; once you approve, the token is read from Claude Code's output, never shown."""
    if sys.platform != "darwin":
        fail("--save-token keeps the token in the macOS Keychain; elsewhere, set CLAUDE_CODE_OAUTH_TOKEN")
    print("Making a Claude Code token for --fresh runs. A browser window is opening: approve it. "
          "Waiting up to 5 minutes...", flush=True)
    _, text = in_terminal(["claude", "setup-token"], dict(os.environ), Path.cwd(), wait=300)
    found = TOKEN.search(text.replace("\r", "\n"))    # line by line: nothing from the next line glued on
    token = found[0] if found else getpass.getpass("\nPaste the token it printed (it won't show): ").strip()
    if not token:
        fail("no token given")
    subprocess.run(["security", "add-generic-password", "-U", "-a", getpass.getuser(), "-s", TOKEN_SERVICE,
                    "-w", token], check=True)
    print(f"Saved in the Keychain as '{TOKEN_SERVICE}'. --fresh runs will use it; it lasts a year, and you can "
          "revoke it at https://claude.ai/settings/claude-code.")


def step(number, text):
    print(f"\nStep {number} of {FRESH_STEPS}: {text}", flush=True)


def in_terminal(command, env, cwd, wait, show=None):
    """Run a command in a pseudo-terminal, as if typed in one, so sign-in commands open the browser.
    Wide, so long lines (a token, an address) don't wrap. Returns (exit code or None if it ran out of
    time, everything it printed); show, if given, gets each line as it comes."""
    leader, follower = os.openpty()
    fcntl.ioctl(follower, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))
    process = subprocess.Popen(command, stdin=follower, stdout=follower, stderr=follower, cwd=cwd, env=env)
    os.close(follower)
    output, pending, deadline = "", "", time.monotonic() + wait
    try:
        while time.monotonic() < deadline:
            ready = select.select([leader], [], [], 1)[0]
            if ready:
                try:
                    chunk = os.read(leader, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                text = ANSI.sub("", chunk.decode(errors="replace"))
                output += text
                pending += text
                *lines, pending = pending.replace("\r", "").split("\n")
                for line in lines:
                    if show and line.strip():
                        show(line)
            elif process.poll() is not None:
                break
        # The command can close the terminal a moment before it exits: give it that moment.
        try:
            code = process.wait(timeout=max(1, min(10, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            process.terminate()
            return None, output
    finally:
        os.close(leader)
    return code, output


def sign_in(name, env, run, wait=300):
    """Claude Code's sign-in for one MCP server: it opens the browser, and waits for Authorize. Its
    link is shown too, in case the browser doesn't open."""
    def show(line):
        if line.strip().startswith("https://"):
            print(f"  If no window opened, open this link: {line.strip()}", flush=True)
    started = time.monotonic()
    code, text = in_terminal(["claude", "mcp", "login", name], env, run, wait, show=show)
    if code == 0 and "Authenticated" in text:
        return True
    (run / f"sign-in-{name}.log").write_text(
        f"exit {code} after {time.monotonic() - started:.0f} seconds\n\n{text}")
    print(f"  What it printed is in {run / f'sign-in-{name}.log'}", flush=True)
    return False


def run_fresh(args, servers, run):
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": claude_token()}
    config = BENCH / f"{run.name}-claude"
    env["CLAUDE_CONFIG_DIR"] = str(config)
    try:
        step(1, f"a blank Claude Code, with no MCP servers, connectors or sign-ins ({config})")
        config.mkdir()

        step(2, f"installing as docs/{args.skill}.md says (Install > Claude Code)")
        for command in guide_install(args.skill, args.source):
            print("$", shlex.join(command), flush=True)
            if subprocess.run(command, cwd=run, env=env, check=False).returncode != 0:
                fail(f"that command from docs/{args.skill}.md failed; a new user would be stuck here")
        if not (config / "skills" / args.skill / "SKILL.md").exists():
            fail(f"the guide's commands didn't install {args.skill} for Claude Code")
        listed = subprocess.run(["claude", "mcp", "list"], cwd=run, env=env, capture_output=True, text=True,
                                check=False).stdout
        missing = [name for name in servers if not re.search(rf"^{re.escape(name)}:", listed, re.M)]
        if missing:
            fail(f"the guide doesn't add the MCP server{'s' if len(missing) > 1 else ''} {', '.join(missing)}")

        step(3, "signing in to the MCP servers, as a new user would")
        for name in servers:
            print(f"  {name}: a browser window is opening. Click Authorize. Waiting up to 5 minutes...",
                  flush=True)
            if not sign_in(name, env, run):
                fail(f"signing in to {name} didn't finish within 5 minutes; run again when you can click Authorize")
            print(f"  {name}: signed in.", flush=True)

        if args.prompt:
            step(4, "running the request")
            run_headless("claude", servers, args.prompt, run, env)
        else:
            step(4, "starting Claude Code there: try the skill, then quit it to clean up")
            subprocess.run(["claude"], cwd=run, env=env, check=False)
    finally:
        step(5, "deleting the sign-ins and the blank configuration")
        if sys.platform == "darwin":
            subprocess.run(["security", "delete-generic-password", "-s", keychain_service(config)],
                           capture_output=True, check=False)
        shutil.rmtree(config, ignore_errors=True)
        print(f"Done. The run's folder stays: {run}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("skill", nargs="?")
    parser.add_argument("--agent", choices=[*AGENTS, "none"], default="claude", help="agent to start (default claude)")
    parser.add_argument("--fresh", action="store_true",
                        help="a blank Claude Code, set up and signed in as the guide says, like a new user's")
    parser.add_argument("--save-token", action="store_true", help="save the Claude Code token --fresh runs use")
    parser.add_argument("--source", default=str(ROOT), help="where to install from (default this working copy)")
    parser.add_argument("--prompt", help="run the agent on its own with this request, and report how it went")
    parser.add_argument("files", nargs="*", type=Path, help="files to copy into the folder")
    args = parser.parse_args()
    if args.save_token:
        save_token()
        return
    if not args.skill:
        parser.error("name the skill to try")
    if args.fresh and args.agent != "claude":
        fail("--fresh works with --agent claude for now")
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
    if args.fresh:
        for file in args.files:
            shutil.copy2(file, run)
        run_fresh(args, servers, run)
        return
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
