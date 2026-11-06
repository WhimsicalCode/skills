# Notes for coding agents

This repository holds Whimsical's agent skills. Read [CONVENTIONS.md](CONVENTIONS.md)
before changing a skill and [CONTRIBUTING.md](CONTRIBUTING.md) before adding one.

- Skills live in `skills/<name>/` and contain only what the agent needs at run time.
  Guides for people go in `docs/<name>.md`, tests in `tests/<name>/`, and the Claude
  Code plugin entry (version, MCP servers) in `.claude-plugin/marketplace.json`.
- Run checks from the repository root:
  `uv run --group dev ruff check .`, then `uv run --group dev pytest tests/repo` and
  `uv run --group dev pytest tests/<name>` for each skill you touched.
- Bump the skill's version in `marketplace.json` when you change it.
- Don't run a skill against real Whimsical boards, Mobbin or customer data unless the
  person you're working with asks you to.
