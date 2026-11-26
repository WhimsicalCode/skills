# Working on App Wireframe

For people changing the skill. What it does, and how to install and use it, is in its guide,
[docs/app-wireframe.md](../../docs/app-wireframe.md).

```text
skills/app-wireframe/
  SKILL.md                 the workflow the agent follows
  references/              design rules, layout techniques, review and arrange guides
  scripts/
    wireframes.py          run progress, draft checks, grouping, links, icons, grid
    arrange.py             places dropped screenshots next to their wireframes
    mobbin_download.py     downloads and crops the Mobbin screens of a shortlist
    mobbin_link.py         reads a pasted Mobbin link: app, screen tags, search query
    icon_index.json        icon names, aliases and descriptions for the icon search
tests/app-wireframe/       tests for the scripts
```

Its Claude Code plugin entry, with both MCP servers, is in the repository's
[`marketplace.json`](../../.claude-plugin/marketplace.json). From the repository root:

```sh
uv run --group dev pytest tests/app-wireframe
```

To try a change the way a user would, in a fresh folder with only the skill's MCP servers
connected:

```sh
uv run dev/try.py app-wireframe --agent claude
```

[CONTRIBUTING.md](../../CONTRIBUTING.md) covers the rest.
