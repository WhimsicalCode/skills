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
- A new skill needs a cover for whimsical.com/skills: follow
  [docs/covers/README.md](docs/covers/README.md), then render and look at it.
- A release isn't done when the tag is pushed. whimsical.com/skills only shows a release
  once the website is redeployed, which doesn't happen on its own. After pushing a tag,
  tell the person you're working with that the website needs redeploying, and keep
  reminding them until they say it's done; otherwise the site falls behind the skills.
  Tag from an up-to-date `main` (`git pull` first), so the release has what was merged.
- Don't run a skill against real Whimsical boards, Mobbin or customer data unless the
  person you're working with asks you to.
