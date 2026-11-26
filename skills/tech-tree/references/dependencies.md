# Judging dependencies and groups

The tree is only as good as its dependencies. Each one becomes an arrow, and every arrow is
something the reader has to follow, so put in the ones that matter and no more.

## What counts as a dependency

B needs A when **B can't start, or would have to be redone, until A is done**:

- B uses what A makes: the dashboard needs the data model it reads; the sauce needs the yolks.
- B decides something A settles: you can't price the plan before choosing the vendor.
- Someone said so: an arrow on the board, or a card saying "after X", "blocked by X",
  "once X is live", "depends on X".

Not dependencies:

- **Better after.** It would be nicer to write the docs after the feature settles, but they can
  start now. Leave it out, or mention it in the report.
- **Same person or team.** Two tasks owned by one person aren't in order because of that; who
  does what when is planning, not the tree.
- **Same topic.** Related tasks aren't in order unless one needs the other. Put them in a group
  if they also go side by side (below).
- **Implied.** If C needs B and B needs A, C needs A through B: don't add the arrow. Each task
  points to what it needs directly.

When you're unsure, leave it out and list it as a question in Step 3. A missing arrow is easy to
add; a wrong one sends the reader the wrong way.

## Explicit and inferred

- **Explicit**: drawn on the board or written on a card. Keep them, unless one is plainly wrong
  (a loop, or a task needing something that comes after it); then ask.
- **Inferred**: your judgement from what the tasks are. Keep a short reason for each ("the KPI
  dashboard reads the metrics layer") and show them to the user before drawing.

## Groups

A group is a dashed rectangle around tasks that belong together and can be done side by side.
Make one when the tasks:

1. are the same kind of work (the shopping; the ingestion jobs; the launch emails),
2. don't need each other, and
3. are needed at about the same time: the things that need them come in the same column or
   close to it.

Keep groups to 2 to 5 tasks, and don't group everything. A group whose tasks are needed far
apart (one needed now, another only at the end) pulls the late one forward and draws a long
arrow across the tree: leave that one out of the group.

An arrow to a group means every task in it is needed for what it points to, and the tree draws
one arrow instead of several. That's a good reason to group tasks that all feed the same next
step.

## Status

Status comes from the board (`tree-format.md`), not from the dependencies: a task in "In
progress" is `doing` even if what it needs isn't done. Don't change a status to make the tree
look tidier.
