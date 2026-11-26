# Working on Website Sitemap

For people changing the skill. What it does, and how to install and use it, is in its guide,
[docs/website-sitemap.md](../../docs/website-sitemap.md).

```text
skills/website-sitemap/
  SKILL.md              the workflow the agent follows
  scripts/
    sitemap.py          reads sitemaps, builds the tree, chooses what fits, writes the diagram text
tests/website-sitemap/  tests for the script, offline, with fictional sites
```

Its Claude Code plugin entry, with the Whimsical MCP server, is in the repository's
[`marketplace.json`](../../.claude-plugin/marketplace.json). From the repository root:

```sh
uv run --group dev pytest tests/website-sitemap
```

To try a change the way a user would, in a fresh folder with only the skill's MCP servers
connected:

```sh
uv run dev/try.py website-sitemap --agent claude
```

The script must keep running on Python 3.9, which a test checks. [CONTRIBUTING.md](../../CONTRIBUTING.md)
covers the rest.
