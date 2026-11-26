# tree.json

`tree.json` is your reading of the source: the tasks, the groups and the dependencies. The script
checks it and fails with a reason when something's off (an id that isn't a task, a loop). How to
read each source into it is in `source-whimsical.md` and `source-linear.md`.

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

- **tasks**: one per card or issue. The id is yours: short, lowercase, unique, and different from
  every group's id. `title` is what the card will say. `status` is `todo`, `doing` or `done`. The
  script works out the rest: a `todo` task whose needs are all done is "start now" (green), the
  others are "waiting" (white).

  A task can also have `url`, its address in the source (`https://...`), and `ref`, a short name
  for it (`ENG-142`): its card then links to it. Use them for Linear issues.
- **groups**: 2 to 5 tasks drawn side by side in a dashed rectangle with a label (see
  `dependencies.md` for when). A task is in one group at most, and tasks of one group can't
  need each other.
- **edges**: `[A, B]` means B needs A. Either end can be a task or a group; an edge to a group
  means every task in it needs A, and an edge from a group means B needs every task in it. You
  can also list an edge to each task of a group: the script merges those into one arrow.
