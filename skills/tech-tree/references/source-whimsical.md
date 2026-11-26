# Reading a Whimsical board

Read it all with `fetch` (`expand_groups: true`, `detail: "detailed"`, `spatial: false`,
`limit: 200`), following the `cursor` until there are no more pages. It lists rows of
`type,id,parentId,x,y,width,height,color,...,text`, then the arrows, one per line, as
`<id>: <from id> -- <to id> ...`.

- **Tasks** are cards: rows of type `note` (note cards) or `task` (older task cards). Sticky
  notes (`simple-note` or `sticky`), text and shapes are not tasks. If the board has no cards,
  only sticky notes, text or shapes, say so and ask whether to use those as the tasks.
- **Titles**: the card's title, exactly as on the board. Cards with the same title are separate
  tasks: give them separate ids.
- **Columns** are rows of type `stack`; a card's `parentId` is its column. Map each column's name
  to a status:
  - `done`: Done, Shipped, Live, Released, Complete, Closed, Merged, Fixed, Archived.
  - `doing`: In progress, Doing, WIP, In review, Review, QA, Testing, Blocked.
  - `todo`: anything else (To do, Backlog, Next, Ideas, This week).

  When a name could go either way, say how you read it when you check with the user.
- **Cards outside columns** are `todo`, unless the card says otherwise: a tag like `done` or
  `shipped`, a checklist with every item ticked, or a description that says it's finished.
- **Descriptions**: read them, `fetch` on each card's id, when they might say what a task needs
  ("after the API is live", "blocked by legal"). On a board of more than 60 cards, read the ones
  whose title doesn't say enough.
- **Arrows between two cards** are dependencies someone drew: the card the arrow starts from is
  needed by the one it points to. An arrow with no arrowhead, or pointing both ways, says the
  cards are related, not which comes first: judge it like any other.
- **A rectangle (a `shape`) around two or more cards**, wholly inside it by their x, y, width and
  height, is a group someone drew; its label is the text inside it or right above it.

The tree's board is titled `<board title> tech tree`, in the same folder or team as the source
board if you know it.
