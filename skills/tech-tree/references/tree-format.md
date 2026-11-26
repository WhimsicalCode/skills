# tree.json, and reading a board into it

`tree.json` is your reading of the board: the tasks, the groups and the dependencies. The script
checks it and fails with a reason when something's off (an id that isn't a task, a loop).

```json
{
  "tasks": {
    "buy-pasta":  {"title": "Buy spaghetti", "status": "done"},
    "boil-water": {"title": "Bring a big pot of water to a boil", "status": "doing"},
    "salt-water": {"title": "Salt the water", "status": "todo"},
    "cook-pasta": {"title": "Cook the spaghetti al dente", "status": "todo"},
    "grate":      {"title": "Grate the pecorino", "status": "todo"},
    "yolks":      {"title": "Separate the egg yolks", "status": "todo"},
    "cream":      {"title": "Whisk yolks and pecorino into a cream", "status": "todo"}
  },
  "groups": {
    "sauce-prep": {"label": "Sauce prep", "tasks": ["grate", "yolks"]}
  },
  "edges": [
    ["boil-water", "salt-water"],
    ["salt-water", "cook-pasta"],
    ["buy-pasta", "cook-pasta"],
    ["sauce-prep", "cream"]
  ]
}
```

- **tasks**: one per card. The id is yours: short, lowercase, unique, and different from every
  group's id. `title` is the card's title exactly as on the board. `status` is `todo`, `doing` or
  `done`. The script works out the rest: a `todo` task whose needs are all done is "start now"
  (green), the others are "waiting" (white).
- **groups**: 2 to 5 tasks drawn side by side in a dashed rectangle with a label (see
  `dependencies.md` for when). A task is in one group at most, and tasks of one group can't
  need each other.
- **edges**: `[A, B]` means B needs A. Either end can be a task or a group; an edge to a group
  means every task in it needs A, and an edge from a group means B needs every task in it. You
  can also list an edge to each task of a group: the script merges those into one arrow.

## Reading the board

`fetch` with `detail: "detailed"` lists rows of `type,id,parentId,x,y,width,height,color,...,text`,
then the arrows, one per line, as `<id>: <from id> -- <to id> ...`.

- **Tasks** are cards: rows of type `note` (note cards) or `task` (older task cards). Sticky
  notes (`simple-note` or `sticky`), text and shapes are not tasks.
- **Columns** are rows of type `stack`; a card's `parentId` is its column. Map each column's name
  to a status:
  - `done`: Done, Shipped, Live, Released, Complete, Closed, Merged, Fixed, Archived.
  - `doing`: In progress, Doing, WIP, In review, Review, QA, Testing, Blocked.
  - `todo`: anything else (To do, Backlog, Next, Ideas, This week).

  When a name could go either way, say how you read it in Step 3.
- **Cards outside columns** are `todo`, unless the card says otherwise: a tag like `done` or
  `shipped`, a checklist with every item ticked, or a description that says it's finished.
- **Arrows between two cards** are dependencies someone drew: the card the arrow starts from is
  needed by the one it points to. An arrow with no arrowhead, or pointing both ways, says the
  cards are related, not which comes first: judge it like any other.
- **A rectangle (a `shape`) around two or more cards**, wholly inside it by their x, y, width and
  height, is a group someone drew; its label is the text inside it or right above it.
- Cards with the same title are separate tasks: give them separate ids.
