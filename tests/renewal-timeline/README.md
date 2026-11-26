# Working on Renewal Timeline

For people changing the skill. What it does, and how to install and use it, is in its guide,
[docs/renewal-timeline.md](../../docs/renewal-timeline.md).

```text
skills/renewal-timeline/
  SKILL.md                 the workflow the agent follows
  references/
    event-schema.md        the events.json format
    board-layout.md        what the board looks like, element by element
    summary-template.md    the summary's structure
  scripts/
    build_board.py         checks events.json, writes the Whimsical calls
  examples/                a small example and a full deal, both fictional
tests/renewal-timeline/    tests for the script (fixtures/: a real board read, fictional data)
```

Its Claude Code plugin entry, with the Whimsical MCP server, is in the repository's
[`marketplace.json`](../../.claude-plugin/marketplace.json). From the repository root:

```sh
uv run --group dev pytest tests/renewal-timeline
```

To try a change the way a user would, in a fresh folder with only the skill's MCP servers
connected:

```sh
uv run dev/try.py renewal-timeline --agent claude
```

The script must keep running on Python 3.9, which a test checks. [CONTRIBUTING.md](../../CONTRIBUTING.md)
covers the rest.
