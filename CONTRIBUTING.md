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
- Try the change in a real run, not only the tests. To install your working copy:
  - Claude Code: `/plugin marketplace add ./` from the repository root, then
    `/plugin install <name>@whimsical`. Run `/plugin marketplace update whimsical` after
    each change.
  - Other agents: `npx skills add ./ --skill <name> --agent <agent>`.
- Say in the pull request which agents and models you tried it with.

## Adding a skill

1. Create `skills/<name>/SKILL.md`. The folder name is the skill's `name`.
2. Add its entry to `.claude-plugin/marketplace.json`, with `"source": "./"`,
   `"strict": false`, `"skills": ["./skills/<name>"]`, a `version` and the
   `mcpServers` it needs. Copy an existing entry.
3. Write its guide in `docs/<name>.md`: what it does, an example prompt and result, what
   it needs, how to install it in each agent, how to use it, privacy. Copy an existing
   guide's structure.
4. Add its tests in `tests/<name>/`.
5. Add a row to the skill table in `README.md`, and its owners to `.github/CODEOWNERS`.

`tests/repo/` fails until steps 1 to 5 are done, and lists what's missing.

## Releasing

A release publishes a zip of every skill, for the Claude apps and for agents without a
skills installer. Links to `releases/latest/download/<name>.zip` always point to the
newest one. After merging to `main`, tag the date and push the tag:

```sh
git tag v2026.11.06 && git push origin v2026.11.06
```

Add a suffix for a second release on the same day, like `v2026.11.06.2`. Users of the
Claude Code marketplace get updates from `main` without a release.
