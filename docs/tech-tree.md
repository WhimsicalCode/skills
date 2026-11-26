![Any to-do list, as a tech tree.](covers/tech-tree.png)

# Tech Tree

Turn a [Whimsical](https://whimsical.com) board of tasks, a kanban, or Linear issues into a tech
tree: each task one column after what it needs, so the order of the work reads at a glance, with
what can start now, what's waiting on what, which tasks run side by side, and the critical path.

```text
Turn this board into a tech tree: https://whimsical.com/acme-launch-...
```

![A carbonara recipe as a tech tree: the critical path from boiling the water to plating runs in orange across the middle, the shopping, the guanciale and the egg sauce feed into it from below, and the three sauce-prep tasks sit side by side in a dashed rectangle](tech-tree.png)

Your agent reads every task, from the cards on a Whimsical board or the issues of a Linear
project, cycle or team, works out which tasks block which, checks the dependencies it inferred
with you, and draws the tree on a new board, laid out like a metro map: lines of tasks run left
to right, and arrows bend as little as they can and cross as rarely as they can.

## What you'll get

A new board called `<Board, project or cycle> tech tree`, with:

- **Every task as a card**, one column after the last thing it needs. Cards are coloured by where
  they stand: green to start now, yellow in progress, white waiting, grey done. A card made from
  a Linear issue starts with its identifier (`ENG-142`) and links to it.
- **An arrow from each task to what needs it.** Only direct needs: if C needs B and B needs A,
  there's no arrow from A to C.
- **Groups**: similar tasks to do side by side, like the shopping before a recipe, in a dashed
  rectangle with a label. One arrow to the rectangle stands for an arrow to each of its cards.
- **The critical path** in orange, drawn on top: the longest chain of unfinished tasks, the one
  that decides how soon it's all done.
- **A key** above the tree, and a line saying how long it took.

The source isn't changed: not the board, not the issues.

## How it lays out the tree

A tech tree is only useful if you can follow its arrows, so the layout is built for that, with
one priority above all: as few crossing arrows as it can, then as few bends.

1. **Columns.** Each task goes one column after the last thing it needs, with the arrows as short
   as they can be (network simplex, as in Graphviz).
2. **Order.** Within each column, cards are ordered to cross as few arrows as possible, the way
   Graphviz and Mermaid order theirs.
3. **Rows.** Keeping that order, cards take rows that line up as many arrows as possible, so they
   run straight, like lines on a metro map. The critical path starts on one row.
4. **Arrows.** Each arrow is one of the shapes Whimsical draws by itself: straight, an L with one
   bend, or a Z or U with two. Arrows never cross a card, and never run along another arrow:
   each side of a card has a few slots, one arrow each.
5. **Polish.** Last, cards are moved the way a person tidying the board would: to a better row, a
   swap with a card in their column, or onto another card's row, pushing it aside. A move stays
   if the tree gets clearer.

If an arrow still can't avoid a card, it's drawn red and the agent looks at it. On the trees
we've tried, none were left.

## What it reads

### From a Whimsical board

- **Tasks** are the board's cards. Sticky notes, text and shapes aren't tasks; if the board has
  only those, the agent asks before using them.
- **Status** comes from the cards' columns: Done, Shipped or Live is done; In progress, Review or
  QA is in progress; anything else is to do. A done tag or a fully ticked checklist counts too.
- **Dependencies** come from arrows already on the board, from what the cards say ("after the
  API is live", "blocked by legal"), and from the agent's judgement.
- **Groups** come from rectangles already drawn around cards, and from the agent's judgement.

### From Linear

- **Tasks** are the issues of a project, a cycle, a team, a label, or the issues you list or link.
  Canceled and duplicate issues are left out.
- **Status** comes from each issue's workflow state: completed is done, started (In Progress, In
  Review) is in progress, the rest is to do.
- **Dependencies** come from the issues' "blocks" and "blocked by" relations. An issue from
  outside the set that blocks one in it is drawn too, and the agent tells you which.
- **Groups** come from sub-issues of one parent.

Either way, the agent only adds a dependency of its own when a task can't start without the
other, and shows you those, with why, before drawing.

## Status

This is a new project, written mostly by coding agents. We've tried it on Whimsical boards of 15
to 30 tasks, in Claude Code. The Linear source is new and hasn't been tried on a real Linear
workspace yet. In Codex, it reads the source and lays the tree out, but can't draw it yet: Codex
doesn't offer the Whimsical MCP's `edit` tool, which the drawing needs. If something breaks,
please [open an issue](https://github.com/WhimsicalCode/skills/issues/new/choose).

## Requirements

- An agent that supports skills and remote MCP servers, such as
  [Claude Code](https://claude.com/claude-code) or Cursor.
- A [Whimsical](https://whimsical.com) account, connected through the
  [Whimsical MCP](https://whimsical.com/learn/integrations/mcp).
- For Linear issues, a [Linear](https://linear.app) account, connected through the
  [Linear MCP](https://linear.app/docs/mcp).
- Python 3.9 or later, with nothing to install.

## Install

The skill uses two MCP servers: Whimsical, `https://mcp.whimsical.com/mcp`, and, for Linear
issues, Linear, `https://mcp.linear.app/mcp`.

### Claude Code

With [Node.js](https://nodejs.org) installed, run this in a terminal:

```sh
npx skills add WhimsicalCode/skills --skill tech-tree --agent claude-code -g
claude mcp add --transport http --scope user whimsical https://mcp.whimsical.com/mcp
claude mcp add --transport http --scope user linear https://mcp.linear.app/mcp
```

`-g` makes the skill available in every folder. Skip a `claude mcp add` line if
`claude mcp list` already shows that server, and the Linear one if you won't use Linear. Then
start Claude Code, run `/mcp`, and sign in.

Or install it as a plugin, which adds both MCP servers for you:

```text
/plugin marketplace add WhimsicalCode/skills
/plugin install tech-tree@whimsical
```

If you already had Whimsical or Linear configured, you'll see it twice in `/mcp`; disable one.

### Claude apps (claude.ai and the desktop app)

Not tested there yet. If you try it, please
[tell us how it went](https://github.com/WhimsicalCode/skills/issues).

1. Download
   [`tech-tree.zip`](https://github.com/WhimsicalCode/skills/releases/latest/download/tech-tree.zip).
2. In Claude, open **Customize** (on claude.ai, [claude.ai/customize/skills](https://claude.ai/customize/skills)),
   click **Add**, then **Upload skill**, drop the zip and click **Upload**.
3. Still in **Customize**, under **Connectors**, add Whimsical, and Linear if you'll use it.

### Other agents (Cursor, Codex, GitHub Copilot, Gemini CLI and more)

With [Node.js](https://nodejs.org) installed, run this in a terminal:

```sh
npx skills add WhimsicalCode/skills --skill tech-tree --agent cursor -g
```

Replace `cursor` with `codex`, `github-copilot`, `gemini-cli` or
[another agent's name](https://github.com/vercel-labs/skills/blob/main/docs/agents.md).
This copies the skill where your agent looks for skills, using the open
[skills](https://github.com/vercel-labs/skills) installer. Without Node.js, unzip
[`tech-tree.zip`](https://github.com/WhimsicalCode/skills/releases/latest/download/tech-tree.zip)
into that folder yourself. Either way, then add the Whimsical MCP server, and Linear's if you'll
use it, following your agent's MCP guide, or
[Whimsical's](https://whimsical.com/learn/integrations/mcp).

## Use it

Start your agent in the folder where you want the working files, then ask in plain language:

```text
Turn this board into a tech tree: https://whimsical.com/...
What order should we do these tasks in? https://whimsical.com/...
Make a tech tree of our Q3 launch project in Linear
What's blocking what in the current cycle of the Platform team?
```

The agent shows you the dependencies it inferred before drawing; say what's wrong and it
redraws the plan. To skip that, say so ("don't ask, I'll review the board"). It will probably
ask permission for each tool the first time; allowing the Whimsical and Linear tools and
`python3` for the session keeps it moving.

Each source gets a folder, `tech-trees/<name>/`: the agent's reading of it (`tree.json`) and the
layout (`plan.json`). To redraw after a change, ask again: the agent updates `tree.json` and
draws the tree on a new board.

## How it works

```text
 Whimsical board                                       tree.json
 or Linear issues  ─►  your agent reads the tasks  ─►  (tasks, groups, dependencies)
                                                          │
                                                          ▼
                                                   techtree.py layout  ─►  plan.json
                                                                              │
                                                                              ▼
                                                          new Whimsical board, drawn as planned
```

1. The agent reads the source and writes `tree.json`: every task with its status, the groups,
   and the dependencies.
2. `techtree.py layout` checks it (unknown ids, loops), drops implied arrows, finds the critical
   path and lays the tree out, deterministically: the same tree always gets the same drawing.
   It writes every card, rectangle and arrow as Whimsical edit operations.
3. The agent creates the board and sends the operations as they are, then adds the footer and
   checks a snapshot.

The script uses only Python's standard library and never calls Whimsical or Linear.

## Privacy

The skill doesn't collect anything, and its script doesn't use the network. Your agent reads
Linear through Linear's MCP server, under [Linear's privacy policy](https://linear.app/privacy),
and reads and draws boards through Whimsical's MCP server, under
[Whimsical's privacy policy](https://whimsical.com/terms/privacy).

## Development

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

Its Claude Code plugin entry, with the Whimsical and Linear MCP servers, is in the repository's
[`marketplace.json`](../.claude-plugin/marketplace.json). From the repository root:

```sh
uv run --group dev pytest tests/tech-tree
```

To try a change the way a user would, in a fresh folder with only the skill's MCP servers
connected:

```sh
uv run dev/try.py tech-tree --agent claude
```
