# Working on Tech Tree

For people changing the skill. What it does, and how to install and use it, is in its guide,
[docs/tech-tree.md](../../docs/tech-tree.md).

```text
skills/tech-tree/
  SKILL.md                  the workflow the agent follows
  references/
    tree-format.md          tree.json, the agent's reading of the source
    source-whimsical.md     how to read a Whimsical board
    source-linear.md        how to read Linear issues
    dependencies.md         how to judge dependencies and groups
  scripts/
    techtree.py             checks the tree and lays it out: columns, order, rows, arrows, polish
tests/tech-tree/            tests for the script, offline, with three example trees
```

Its Claude Code plugin entry, with the Whimsical MCP server, is in the repository's
[`marketplace.json`](../../.claude-plugin/marketplace.json). From the repository root:

```sh
uv run --group dev pytest tests/tech-tree
```

To try a change the way a user would, in a fresh folder with only the skill's MCP servers
connected, and Linear's to try reading Linear:

```sh
uv run dev/try.py tech-tree --agent claude
uv run dev/try.py tech-tree --agent claude --mcp linear=https://mcp.linear.app/mcp
```

[CONTRIBUTING.md](../../CONTRIBUTING.md) covers the rest.
