# Contributing

Thanks for helping. Bug reports from real runs are the most useful contribution: say which
skill, which agent and model, what you asked and what happened. Use the
[issue forms](https://github.com/WhimsicalCode/skills/issues/new/choose).

## Setup

You need [uv](https://docs.astral.sh/uv/) and git. From the repository root:

```sh
uv sync --group dev
```

## Before opening a pull request

```sh
uv run --group dev ruff check .
for dir in tests/*/; do uv run --group dev pytest "$dir" || break; done
```

Each `tests/` folder runs in its own pytest process, because every skill's tests have
their own `conftest.py`. To work on one skill, run `uv run --group dev pytest tests/<name>`
and `uv run --group dev pytest tests/repo`.

If you have Claude Code, also run `claude plugin validate .`.

## Changing a skill

- Follow [CONVENTIONS.md](CONVENTIONS.md).
- Bump the skill's version in `.claude-plugin/marketplace.json`.
- Update its guide in `docs/<name>.md` if what users see or do changes.
- Try the change in a real run, not only the tests, in Claude Code and in Codex:

  ```sh
  uv run dev/try.py <name> --agent claude    # or --agent codex
  ```

  It installs your working copy into a new folder in `~/skill-bench` with the guide's
  `npx skills add` command, connects only the MCP servers in the skill's `marketplace.json`
  entry, and starts the agent there. Add files to copy them into the folder. To try the
  published version instead, name the skill `WhimsicalCode/skills/<name>`. With
  `--prompt "<what a user would ask>"`, the agent runs on its own and the script reports
  its answer, how long it took and anything it wasn't allowed to do.
- Say in the pull request which agents and models you tried it with.

## Adding a skill

1. Create `skills/<name>/SKILL.md`. The folder name is the skill's `name`.
2. Add its entry to `.claude-plugin/marketplace.json`, with `"source": "./"`,
   `"strict": false`, `"skills": ["./skills/<name>"]`, a `version` and the
   `mcpServers` it needs. Copy an existing entry.
3. Write its guide in `docs/<name>.md`: what it does, an example prompt and result, what
   it needs, how to install it in each agent, how to use it, privacy. Copy an existing
   guide's structure. Its intro, before the first `##`, is also its summary on
   whimsical.com (see [CONVENTIONS.md](CONVENTIONS.md#on-whimsicalcom)).
4. Make its cover in `docs/covers/`, following
   [docs/covers/README.md](docs/covers/README.md).
5. Add its tests in `tests/<name>/`.
6. Add a row to the skill table in `README.md`, and its owners to `.github/CODEOWNERS`.

`tests/repo/` fails until steps 1 to 6 are done, and lists what's missing.

## Releasing

A release publishes a zip of every skill, for the Claude apps and for agents without a
skills installer. Links to `releases/latest/download/<name>.zip` always point to the
newest one. After merging to `main`, update your local `main`, then tag the date and push
the tag:

```sh
git checkout main && git pull
git tag v2026.11.06 && git push origin v2026.11.06
```

Add a suffix for a second release on the same day, like `v2026.11.06.2`. Users of the
Claude Code marketplace get updates from `main` without a release.

Then redeploy the website. [whimsical.com/skills](https://whimsical.com/skills) shows the
skills as they are in the latest release, but only from the website's next deploy, and a
release doesn't trigger one. Until it's redeployed, the site still shows the previous
release.
