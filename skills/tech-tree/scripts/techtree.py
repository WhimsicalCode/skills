#!/usr/bin/env python3
"""Lay out a tech tree for a Whimsical board: where every card, group and arrow goes.

    python3 techtree.py start <folder>                  when the run begins
    python3 techtree.py layout <tree.json> --out <plan.json>
    python3 techtree.py footer <folder> <plan.json>     the last thing to add to the board

The tree is the agent's reading of the board: tasks, groups of tasks to do side by side, and
which task needs which. A tech tree reads left to right in columns, one per tier: a task sits in
a column after everything it needs. The layout is built to be read like one, with as few
crossing arrows (hops) and as few bends (elbows) as it can manage:

1. Columns, by network simplex (as in Graphviz): every arrow points one or more columns ahead,
   and the arrows are as short as they can be.
2. Rows on a grid of half rows, so a card can line up with a card or with the gap between two
   cards of a group. The critical path, the longest chain of unfinished tasks, takes one row.
3. A seeded search (simulated annealing) moves cards between rows and columns, swaps them and
   reorders groups, keeping the drawing with the lowest score: hops and elbows first, arrows
   through cards never, then length and height.

Every arrow takes a route Whimsical draws by itself: straight, one elbow, or two. The plan lists
the edit operations to send, in order: rectangles before the cards on them, cards before the
arrows between them, and the critical path last, so it's drawn on top.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

CARD_W, CARD_H = 216, 108
PAD, LABEL = 16, 30          # a group's padding around its cards, and its label above it
ROW_GAP, COL_GAP = 80, 140   # between two rows of cards, and between two columns
COLORS = {"done": "light-gray", "doing": "yellow", "ready": "green", "waiting": "white"}
SKILL = "tech-tree"
SKILL_URL = "https://whimsical.com/skills/tech-tree"
KEY = [("ready", "Start now"), ("doing", "In progress"), ("waiting", "Waiting"), ("done", "Done")]
KEY_ROW, KEY_SWATCH = 48, (48, 28)            # the key's rows, and the colour swatch in each


def fail(message):
    sys.exit(f"techtree: {message}")


# --- The tree ----------------------------------------------------------------------------------

def load_tree(path):
    """Read and check a tree.json: tasks, groups and edges, all referring to each other by id."""
    try:
        tree = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"can't read {path}: {error}")
    tasks, groups, edges = tree.get("tasks"), tree.get("groups", {}), tree.get("edges", [])
    if not isinstance(tasks, dict) or not tasks:
        fail("the tree has no tasks")
    for t, spec in tasks.items():
        if not spec.get("title"):
            fail(f"task {t} has no title")
        if spec.get("status", "todo") not in ("todo", "doing", "done"):
            fail(f"task {t} has status {spec['status']!r}; use todo, doing or done")
        if "url" in spec and not str(spec["url"]).startswith("https://"):
            fail(f"task {t} has url {spec['url']!r}; give its https:// address, or leave it out")
    seen = {}
    for g, spec in groups.items():
        if g in tasks:
            fail(f"{g} is both a task and a group; give the group another id")
        if len(spec.get("tasks", [])) < 2:
            fail(f"group {g} needs at least two tasks")
        for t in spec["tasks"]:
            if t not in tasks:
                fail(f"group {g} lists {t}, which isn't a task")
            if t in seen:
                fail(f"{t} is in both {seen[t]} and {g}; a task is in one group at most")
            seen[t] = g
    for e in edges:
        if len(e) != 2 or any(x not in tasks and x not in groups for x in e):
            fail(f"edge {e} doesn't join two tasks or groups")
        if e[0] == e[1]:
            fail(f"edge {e} joins {e[0]} to itself")
    return tree


class Tree:
    """The tasks and groups, with the edges merged and trimmed for drawing."""

    def __init__(self, tree):
        self.tasks = tree["tasks"]
        self.groups = tree.get("groups", {})
        self.group_of = {t: g for g, spec in self.groups.items() for t in spec["tasks"]}
        edges = list(dict.fromkeys(tuple(e) for e in tree.get("edges", [])))
        for a, b in edges:
            if self.unit(a) == self.unit(b):
                fail(f"{a} and {b} are in the same group, so one can't need the other; split the group")
        self.check_cycles(edges)
        self.edges, self.merged = self.merge(edges)
        self.edges, self.dropped = self.trim(self.edges)
        self.needs = {t: set() for t in self.tasks}
        for ta, tb in self.task_edges(self.edges):
            self.needs[tb].add(ta)
        self.state = {t: self.status(t) for t in self.tasks}
        self.critical, self.ties = self.critical_path()
        pairs = set(zip(self.critical, self.critical[1:]))
        self.spine = {e for e in self.edges
                      if any((x, y) in pairs for x in self.members(e[0]) for y in self.members(e[1]))}

    def unit(self, x):
        return x if x in self.groups else self.group_of.get(x, x)

    def members(self, x):
        return self.groups[x]["tasks"] if x in self.groups else [x]

    def task_edges(self, edges):
        return {(ta, tb) for a, b in edges for ta in self.members(a) for tb in self.members(b)}

    def check_cycles(self, edges):
        """Fail on a loop, naming it: the agent has to decide which dependency is wrong."""
        out = {}
        for a, b in edges:
            out.setdefault(self.unit(a), set()).add(self.unit(b))
        state, path = {}, []

        def visit(u):
            state[u] = "open"
            path.append(u)
            for w in sorted(out.get(u, ())):
                if state.get(w) == "open":
                    loop = path[path.index(w):] + [w]
                    fail("these tasks need each other in a loop: " + " -> ".join(loop))
                if w not in state:
                    visit(w)
            path.pop()
            state[u] = "closed"

        for u in sorted(out):
            if u not in state:
                visit(u)

    def merge(self, edges):
        """One arrow to a group stands for an arrow to each of its cards: merge those, both ways."""
        merged, changed = [], True
        while changed:
            changed = False
            for g, spec in self.groups.items():
                cards = spec["tasks"]
                for x in sorted({a for a, b in edges if b in cards}):
                    if self.unit(x) != g and all((x, m) in edges for m in cards):
                        edges = [e for e in edges if not (e[0] == x and e[1] in cards)] + [(x, g)]
                        merged.append((x, g))
                        changed = True
                for x in sorted({b for a, b in edges if a in cards}):
                    if self.unit(x) != g and all((m, x) in edges for m in cards):
                        edges = [e for e in edges if not (e[1] == x and e[0] in cards)] + [(g, x)]
                        merged.append((g, x))
                        changed = True
        return edges, merged

    def trim(self, edges):
        """Drop arrows another path implies: with A to B and B to C, A to C says nothing more."""
        dropped = []
        for e in list(edges):
            rest = self.task_edges([x for x in edges if x != e])
            out = {}
            for a, b in rest:
                out.setdefault(a, set()).add(b)
            if all(self.reaches(out, ta, tb) for ta in self.members(e[0]) for tb in self.members(e[1])):
                edges.remove(e)
                dropped.append(e)
        return edges, dropped

    @staticmethod
    def reaches(out, start, goal):
        seen, todo = {start}, [start]
        while todo:
            for b in out.get(todo.pop(), ()):
                if b == goal:
                    return True
                if b not in seen:
                    seen.add(b)
                    todo.append(b)
        return False

    def status(self, t):
        s = self.tasks[t].get("status", "todo")
        if s in ("done", "doing"):
            return s
        return "ready" if all(self.tasks[p].get("status") == "done" for p in self.needs[t]) else "waiting"

    def critical_path(self):
        """The longest chain of unfinished tasks, and how many chains tie with it."""
        order = list(self.tasks)
        open_ = [t for t in order if self.tasks[t].get("status") != "done"]
        if not open_:
            return [], 0
        best = {}
        for t in self.topological(open_):
            chains = [c for p in sorted(self.needs[t], key=order.index) if p in best for c in best[p]]
            n = max((len(c) for c in chains), default=0)
            best[t] = [c + [t] for c in chains if len(c) == n][:50] or [[t]]
        longest = max(len(c[0]) for c in best.values())
        tied = [c for t in open_ for c in best[t] if len(c) == longest]
        return tied[0], len(tied)

    def topological(self, nodes):
        nodes = set(nodes)
        done, out = set(), []

        def visit(t):
            if t in done:
                return
            done.add(t)
            for p in sorted(self.needs[t] & nodes):
                visit(p)
            out.append(t)

        for t in self.tasks:
            if t in nodes:
                visit(t)
        return out


# --- 1. Columns: network simplex -----------------------------------------------------------------

def rank_nodes(nodes, edges):
    """A column for each node of a DAG, every edge pointing at least one column ahead, and the
    weighted total length of the edges as short as it can be. This is network simplex, as in
    Graphviz and dagre (Gansner et al., 1993). edges maps (u, v) to a weight."""
    out = {n: [] for n in nodes}
    for u, v in edges:
        out[u].append(v)
    rank = {}
    for n in reversed(topo_order(nodes, edges)):     # start: each node just before its successors
        rank[n] = min((rank[w] - 1 for w in out[n]), default=0)
    for comp in components(nodes, edges):
        comp_edges = [e for e in edges if e[0] in comp]
        simplex(comp, comp_edges, edges, rank)
        low = min(rank[n] for n in comp)
        for n in comp:
            rank[n] -= low
    return rank


def topo_order(nodes, edges):
    indeg = {n: 0 for n in nodes}
    out = {n: [] for n in nodes}
    for u, v in edges:
        indeg[v] += 1
        out[u].append(v)
    ready = [n for n in nodes if indeg[n] == 0]
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for w in out[n]:
            indeg[w] -= 1
            if indeg[w] == 0:
                ready.append(w)
    return order


def components(nodes, edges):
    parent = {n: n for n in nodes}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for u, v in edges:
        parent[find(u)] = find(v)
    comps = {}
    for n in nodes:
        comps.setdefault(find(n), []).append(n)
    return list(comps.values())


def simplex(nodes, edges, weights, rank):
    """Network simplex on one connected component, changing rank in place."""
    if len(nodes) < 2:
        return

    def slack(e):
        return rank[e[1]] - rank[e[0]] - 1

    incident = {n: [] for n in nodes}
    for e in edges:
        incident[e[0]].append(e)
        incident[e[1]].append(e)

    # A feasible spanning tree of tight edges: grow it, shifting it closer whenever it's stuck.
    in_tree, tree = {nodes[0]}, set()

    def grow():
        stack = list(in_tree)
        while stack:
            v = stack.pop()
            for e in incident[v]:
                w = e[1] if e[0] == v else e[0]
                if w not in in_tree and slack(e) == 0:
                    in_tree.add(w)
                    tree.add(e)
                    stack.append(w)

    grow()
    while len(in_tree) < len(nodes):
        e = min((e for e in edges if (e[0] in in_tree) != (e[1] in in_tree)), key=lambda e: (slack(e), e))
        delta = slack(e) if e[0] in in_tree else -slack(e)
        for v in in_tree:
            rank[v] += delta
        grow()

    def side(cut):
        """The nodes on the tail side of a tree edge, once it's cut."""
        adj = {n: [] for n in nodes}
        for a, b in tree:
            if (a, b) != cut:
                adj[a].append(b)
                adj[b].append(a)
        seen, todo = {cut[0]}, [cut[0]]
        while todo:
            for w in adj[todo.pop()]:
                if w not in seen:
                    seen.add(w)
                    todo.append(w)
        return seen

    # Swap a tree edge with a negative cut value for the slackest edge across, until none is left.
    for _ in range(10 * len(nodes) * len(nodes)):
        leaving = tail = None
        for t in sorted(tree):
            tail_side = side(t)
            cut = sum(weights[e] * ((e[0] in tail_side) - (e[1] in tail_side)) for e in edges)
            if cut < 0:
                leaving, tail = t, tail_side
                break
        if leaving is None:
            return
        entering = min((e for e in edges if e not in tree and e[0] not in tail and e[1] in tail),
                       key=lambda e: (slack(e), e))
        tree.remove(leaving)
        tree.add(entering)
        # Every tree edge tight again: re-rank from one node along the tree.
        adj = {n: [] for n in nodes}
        for a, b in tree:
            adj[a].append((b, 1))
            adj[b].append((a, -1))
        seen, todo = {nodes[0]}, [nodes[0]]
        while todo:
            v = todo.pop()
            for w, d in adj[v]:
                if w not in seen:
                    rank[w] = rank[v] + d
                    seen.add(w)
                    todo.append(w)


# --- 2. The grid: rows, arrows and the score -------------------------------------------------------

HALF = (CARD_H + ROW_GAP) / 2         # a half row: cards sit on half rows, two apart at least
COL_W = CARD_W + 2 * PAD + COL_GAP    # a column, with the gap after it
SIDE_SLOTS = (0.5, 0.3, 0.7)                  # where arrows may meet a card's left or right side
END_SLOTS = (0.5, 0.3, 0.7)                   # and its top or bottom
U_DROP = 48                                   # how far a U runs below (or above) the cards it joins

# What the layout minimises. Hops and elbows are what the reader sees; the rest keeps it tidy.
COST = {
    "through": 10000,     # an arrow through a card or a label: never
    "overlap": 10000,     # two arrows along the same line, or meeting end to end: never
    "group": 60,          # an arrow through a rectangle it doesn't belong to
    "hop": 10,            # two arrows crossing: much the worst thing a reader has to follow
    "elbow": 2,           # a bend
    "spine": 1,           # a bend on the critical path, on top of its elbow: fine if it reads
    "length": 0.01,       # per pixel of arrow: 200 pixels cost as much as an elbow
    "height": 0.01,       # per pixel of drawing height
}


class Grid:
    """A tech tree on a grid of columns and half rows, placed one of two ways, its arrows routed
    as on a metro map.

    "layers" places cards the way Graphviz does: first an order in each column that crosses as
    few arrows as it can, then rows, keeping that order, that line up as many arrows as it can.
    "tracks" works the other way round: first the most arrows that can be straight at once, as
    tracks of cards in one row, then the tracks stacked to cross little. Layers is quicker and
    usually wins; the layout tries tracks too when layers leaves an arrow in trouble."""

    def __init__(self, tree, strategy="layers"):
        self.tree = t = tree
        self.units = list(dict.fromkeys(t.unit(x) for x in t.tasks))
        weights = {}
        for a, b in t.edges:
            key = (t.unit(a), t.unit(b))
            weights[key] = weights.get(key, 0) + (2 if (a, b) in t.spine else 1)
        self.col = rank_nodes(self.units, weights)
        self.cards = {u: list(t.members(u)) for u in self.units}   # a group's cards, top to bottom
        self.unit_of = {c: u for u in self.units for c in self.cards[u]}
        self.edges = list(t.edges)
        self.spine = [e in t.spine for e in self.edges]
        self.incident = {u: [] for u in self.units}
        self.preds = {u: set() for u in self.units}
        self.succs = {u: set() for u in self.units}
        for i, (a, b) in enumerate(self.edges):
            ua, ub = t.unit(a), t.unit(b)
            self.incident[ua].append(i)
            self.incident[ub].append(i)
            self.preds[ub].add(ua)
            self.succs[ua].add(ub)
        self.spine_units = {t.unit(x) for x in t.critical}
        self.strategy = strategy
        self.h = {}
        if strategy == "tracks":
            self.straight = self.match()
            self.build_tracks()
            self.place()
            self.route_all()
            self.polish_bundles()
        else:
            self.set_h(Layers(self).rows)
            self.straight = {i for i, (a, b) in enumerate(self.edges)
                             if set(self.ports(a, self.spine[i])) & set(self.ports(b, self.spine[i]))}
            self.route_all()

    # --- Where things are -------------------------------------------------------------------------

    def span(self, u, h=None):
        """The half rows a unit takes in its column: from one above its top card to one below
        its bottom card."""
        h = self.h[u] if h is None else h
        return h - 1, h + 2 * len(self.cards[u]) - 1

    def free(self, u, col, h, ignore=()):
        lo, hi = self.span(u, h)
        for v in self.units:
            if v != u and v not in ignore and v in self.h and self.col[v] == col:
                a, b = self.span(v)
                if lo < b and a < hi:
                    return False
        return True

    def card_box(self, card):
        u = self.unit_of[card]
        y = (self.h[u] + 2 * self.cards[u].index(card)) * HALF
        return (self.col[u] * COL_W + PAD, y - CARD_H / 2, CARD_W, CARD_H)

    def group_box(self, g):
        top = self.card_box(self.cards[g][0])
        height = (len(self.cards[g]) - 1) * 2 * HALF + CARD_H + 2 * PAD
        return (self.col[g] * COL_W, top[1] - PAD, CARD_W + 2 * PAD, height)

    def label_box(self, g):
        x, y, w, _ = self.group_box(g)
        return (x, y - LABEL, w, LABEL)

    def box(self, ref):
        return self.group_box(ref) if ref in self.tree.groups else self.card_box(ref)

    def ports(self, ref, spine=False):
        """Where arrows may meet ref's side: a card's middle, or for a group the gaps between its
        cards, so they can't be mistaken for one card's arrows. The critical path may also meet
        a group at its card on the path, to stay straight; it's orange, so it reads."""
        if ref in self.tree.groups:
            h = self.h[ref]
            rows = [h + 2 * i + 1 for i in range(len(self.cards[ref]) - 1)]
            if spine:
                rows += [h + 2 * i for i, c in enumerate(self.cards[ref]) if c in self.tree.critical]
            return [r * HALF for r in rows]
        x, y, w, hh = self.card_box(ref)
        return [y + hh / 2]

    # --- Arrows: the metro's grammar ------------------------------------------------------------
    #
    # A line runs straight from a card's right side to the next card's left side. An arrow between
    # two lines is a transfer: an L with one elbow (out of a side and into a top or bottom, or out
    # of a top or bottom and into a side) when one is clear, or else a Z bending halfway across, or
    # a U under (or over) the cards. Each side has a few slots, one arrow each, so no two arrows
    # ever share a line.

    def side(self, ref, which, at):
        """The point at a slot on one side of ref, and the anchor Whimsical takes for it."""
        x, y, w, h = self.box(ref)
        if which == "right":
            return (x + w, y + at * h), {"rx": 1, "ry": round(at, 4), "a": "x"}
        if which == "left":
            return (x, y + at * h), {"rx": 0, "ry": round(at, 4), "a": "x"}
        if which == "top":
            return (x + at * w, y), {"rx": round(at, 4), "ry": 0, "a": "y"}
        return (x + at * w, y + h), {"rx": round(at, 4), "ry": 1, "a": "y"}

    def side_slots(self, ref, i):
        """Where on its left or right side an arrow may meet ref: a card's slots, or for a group
        the gaps between its cards (and its card on the critical path, for the critical path)."""
        if ref not in self.tree.groups:
            return list(SIDE_SLOTS)
        x, y, w, h = self.box(ref)
        return [(r - y) / h for r in self.ports(ref, self.spine[i])]

    def candidates(self, i):
        """The routes arrow i may take, as (elbows, from anchor, to anchor, points, slots)."""
        a, b = self.edges[i]
        _, ay, _, ah = self.box(a)
        _, by, _, bh = self.box(b)
        out = []
        for sa in self.side_slots(a, i):
            pa, ra = self.side(a, "right", sa)
            for sb in self.side_slots(b, i):
                pb, rb = self.side(b, "left", sb)
                if abs(pa[1] - pb[1]) < 0.5:                 # a line: straight on
                    out.append(route(0, ra, rb, [pa, pb], [(a, "right", sa), (b, "left", sb)]))
                else:                                        # a Z, bending halfway across
                    xm = (pa[0] + pb[0]) / 2
                    out.append(route(2, ra, rb, [pa, (xm, pa[1]), (xm, pb[1]), pb],
                                     [(a, "right", sa), (b, "left", sb)]))
            end = "top" if pa[1] < by else "bottom" if pa[1] > by + bh else None
            for sb in END_SLOTS if end else ():              # out of the side, down or up into b
                pb, rb = self.side(b, end, sb)
                if pa[0] < pb[0]:
                    out.append(route(1, ra, rb, [pa, (pb[0], pa[1]), pb], [(a, "right", sa), (b, end, sb)]))
        for sb in self.side_slots(b, i):
            pb, rb = self.side(b, "left", sb)
            start = "bottom" if pb[1] > ay + ah else "top" if pb[1] < ay else None
            for sa in END_SLOTS if start else ():            # down or up out of a, into b's side
                pa, ra = self.side(a, start, sa)
                if pa[0] < pb[0]:
                    out.append(route(1, ra, rb, [pa, (pa[0], pb[1]), pb], [(a, start, sa), (b, "left", sb)]))
        for under in ("bottom", "top"):                      # a U, when nothing simpler is clear
            for sa in END_SLOTS[:3]:
                pa, ra = self.side(a, under, sa)
                for sb in END_SLOTS[:3]:
                    pb, rb = self.side(b, under, sb)
                    if pa[0] >= pb[0]:
                        continue
                    y = max(pa[1], pb[1]) + U_DROP if under == "bottom" else min(pa[1], pb[1]) - U_DROP
                    out.append(route(2, ra, rb, [pa, (pa[0], y), (pb[0], y), pb], [(a, under, sa), (b, under, sb)]))
        return out

    def obstacles(self, i):
        """What arrow i mustn't cross: cards and labels, and rectangles it isn't part of."""
        a, b = self.edges[i]
        own = set(self.tree.members(a)) | set(self.tree.members(b))
        own_groups = {self.unit_of[c] for c in own} | {a, b}
        cards = [box for c, box in self.card_boxes.items() if c not in own]
        rects = [box for g, box in self.group_boxes.items() if g not in own_groups]
        return cards + self.label_boxes, rects

    def floor(self, i, route):
        """The least route i can cost: its elbows and its length, before anything it runs into."""
        elbow = COST["elbow"] + (COST["spine"] if self.spine[i] else 0)
        return elbow * route[0] + COST["length"] * route[7]

    def route_cost(self, i, route, blocked, rects, limit=float("inf")):
        """What route i would cost, given the other arrows; stops counting once it passes limit."""
        segs, box = route[5], route[6]
        x1, y1, x2, y2 = box
        cost = self.floor(i, route)
        for weight, rects_ in ((COST["through"], blocked), (COST["group"], rects)):
            for bx, by, bw, bh in rects_:
                if x1 <= bx + bw and bx <= x2 and y1 <= by + bh and by <= y2:
                    for sg in segs:
                        cost += weight * hits(sg, (bx, by, bw, bh))
            if cost >= limit:
                return cost
        for j, other in enumerate(self.routes):
            if j == i or other is None or not near(box, other[6], 24):
                continue
            for sg in segs:
                for o in other[5]:
                    cost += COST["overlap"] * overlap(sg, o) + COST["hop"] * crosses(sg, o)
            if cost >= limit:
                return cost
        return cost

    def reroute(self, i):
        """Pick arrow i's cheapest route among the free slots, given the others."""
        if self.routes[i] is not None:
            self.slots.difference_update(self.routes[i][4])
            self.routes[i] = None
        blocked, rects = self.obstacles(i)
        options = [r for r in self.candidates(i) if not any(sl in self.slots for sl in r[4])]
        if not options:                                      # every slot taken: share one rather than fail
            options = self.candidates(i)
        best, best_cost = None, float("inf")
        for r in sorted(options, key=lambda r: self.floor(i, r)):
            if self.floor(i, r) >= best_cost:
                break                                        # nothing after this can do better
            cost = self.route_cost(i, r, blocked, rects, best_cost)
            if cost < best_cost:
                best, best_cost = r, cost
        self.routes[i] = best
        self.slots.update(best[4])

    def flagged(self):
        """Arrows that still run through a card or a label, or along another arrow."""
        out = []
        for i, route in enumerate(self.routes):
            blocked, _ = self.obstacles(i)
            segs, box = route[5], route[6]
            bad = any(hits(s, b) for b in blocked if touches(box, b) for s in segs)
            for j, other in enumerate(self.routes):
                if j != i and near(box, other[6], 24) and any(overlap(s, o) for s in segs for o in other[5]):
                    bad = True
            if bad:
                out.append(i)
        return out

    # --- The score --------------------------------------------------------------------------------

    def score(self):
        """Everything the layout minimises, and the counts behind it."""
        through = group = hops = overlaps = 0
        length = 0.0
        for i, route in enumerate(self.routes):
            blocked, rects = self.obstacles(i)
            segs, box = route[5], route[6]
            through += sum(hits(s, b) for b in blocked if touches(box, b) for s in segs)
            group += sum(hits(s, b) for b in rects if touches(box, b) for s in segs)
            length += route[7]
            for j in range(i + 1, len(self.routes)):
                other = self.routes[j]
                if not near(box, other[6], 24):
                    continue
                for s in segs:
                    for o in other[5]:
                        hops += crosses(s, o)
                        overlaps += overlap(s, o)
        elbows = sum(r[0] for r in self.routes)
        spine_bends = sum(r[0] for r, s in zip(self.routes, self.spine) if s)
        lo = min(self.span(u)[0] for u in self.units)
        hi = max(self.span(u)[1] for u in self.units)
        height = (hi - lo) * HALF
        total = (COST["through"] * through + COST["overlap"] * overlaps + COST["group"] * group
                 + COST["hop"] * hops + COST["elbow"] * elbows + COST["spine"] * spine_bends
                 + COST["length"] * length + COST["height"] * height)
        return total, {"hops": hops, "elbows": elbows, "through_cards": through, "overlaps": overlaps,
                       "through_groups": group, "spine_bends": spine_bends}

    # --- 2. Straight arrows: a matching ---------------------------------------------------------

    def end_ports(self, ref, i):
        """Where arrow i may meet ref on a straight line: a card, or a gap of a group. The
        critical path meets a group at its card on the path, so it runs on through it."""
        if ref not in self.tree.groups:
            return [("card", ref)]
        cards = self.cards[ref]
        if self.spine[i]:
            on = [("card", c) for c in cards if c in self.tree.critical]
            if on:
                return on
        return [("gap", ref, j) for j in range(len(cards) - 1)]

    def match(self):
        """The most arrows that can be straight at once: each card or gap has at most one
        straight arrow in and one out. A maximum flow, the critical path first."""
        straight, used_out, used_in = {}, set(), set()
        spine = [i for i in range(len(self.edges)) if self.spine[i]]
        rest = sorted((i for i in range(len(self.edges)) if not self.spine[i]),
                      key=lambda i: (self.col[self.tree.unit(self.edges[i][1])]
                                     - self.col[self.tree.unit(self.edges[i][0])], i))
        for batch in (spine, rest):
            found = self.max_flow(batch, used_out, used_in)
            for i, (ko, ki) in found.items():
                straight[i] = (ko, ki)
                used_out.add(ko)
                used_in.add(ki)
        return straight

    def max_flow(self, batch, used_out, used_in):
        cap = {}

        def link(u, v):
            cap.setdefault(u, {})[v] = 1
            cap.setdefault(v, {}).setdefault(u, 0)

        for i in batch:
            a, b = self.edges[i]
            outs = [k for k in self.end_ports(a, i) if k not in used_out]
            ins = [k for k in self.end_ports(b, i) if k not in used_in]
            if not outs or not ins:
                continue
            for k in outs:
                link("S", ("o", k))
                link(("o", k), ("a", i))
            link(("a", i), ("b", i))
            for k in ins:
                link(("b", i), ("i", k))
                link(("i", k), "T")
        if "S" not in cap:
            return {}
        while True:                                      # Edmonds and Karp: shortest paths first
            parent, queue = {"S": None}, ["S"]
            while queue and "T" not in parent:
                u = queue.pop(0)
                for v, c in cap[u].items():
                    if c > 0 and v not in parent:
                        parent[v] = u
                        queue.append(v)
            if "T" not in parent:
                break
            v = "T"
            while parent[v] is not None:
                u = parent[v]
                cap[u][v] -= 1
                cap[v][u] += 1
                v = u
        found = {}
        for i in batch:
            if cap.get(("b", i), {}).get(("a", i)) == 1:     # one unit of flow went through i
                ko = next(u[1] for u, c in cap[("a", i)].items() if u != ("b", i) and c == 1)
                ki = next(v[1] for v, c in cap[("b", i)].items() if v != ("a", i) and c == 0
                          and cap[v].get(("b", i)) == 1)
                found[i] = (ko, ki)
        return found

    # --- 3. Tracks and bundles --------------------------------------------------------------------

    def key_col(self, key):
        return self.col[self.unit_of[key[1]]] if key[0] == "card" else self.col[key[1]]

    def key_group(self, key):
        return self.tree.group_of.get(key[1]) if key[0] == "card" else key[1]

    def key_rel(self, key):
        """A key's row in its group, in half rows from the group's top card."""
        if key[0] == "gap":
            return 2 * key[2] + 1
        g = self.tree.group_of.get(key[1])
        return 2 * self.cards[g].index(key[1]) if g else 0

    def build_tracks(self):
        """Chains of straight arrows become tracks, one row each; tracks through one group are
        tied into a bundle. Where they can't fit together, an arrow stops being straight."""
        while True:
            nxt = {ko: ki for ko, ki in self.straight.values()}
            prv = {ki: ko for ko, ki in self.straight.values()}
            keys = [("card", c) for c in self.tree.tasks]
            keys += sorted({k for pair in self.straight.values() for k in pair if k[0] == "gap"})
            tracks = []
            for k in keys:
                if k in prv:
                    continue
                chain = [k]
                while chain[-1] in nxt:
                    chain.append(nxt[chain[-1]])
                tracks.append(chain)
            track_of = {k: t for t, chain in enumerate(tracks) for k in chain}
            cut = self.tie(tracks, track_of)
            if cut is None:
                break
            del self.straight[cut]
        self.tracks, self.track_of = tracks, track_of

    def tie(self, tracks, track_of):
        """Tie tracks into bundles by their groups; return an arrow to make bent if they clash."""
        by_group = {}
        for k in track_of:
            g = self.key_group(k)
            if g:
                by_group.setdefault(g, []).append(k)
        offset, bundle_of, bundles = {}, {}, []
        for t in range(len(tracks)):
            if t in offset:
                continue
            offset[t], bundle_of[t] = 0, len(bundles)
            members, todo = [t], [t]
            while todo:
                u = todo.pop()
                for k in tracks[u]:
                    g = self.key_group(k)
                    if not g:
                        continue
                    top = offset[u] - self.key_rel(k)    # the group's top card row
                    for k2 in by_group[g]:
                        v = track_of[k2]
                        want = top + self.key_rel(k2)
                        if v not in offset:
                            offset[v], bundle_of[v] = want, bundle_of[t]
                            members.append(v)
                            todo.append(v)
                        elif offset[v] != want:
                            return self.arrow_into(k2, tracks[v])
            bundles.append(members)
            clash = self.clash(bundles[-1], tracks, offset)
            if clash is not None:
                return clash
        self.offset, self.bundle_of, self.bundles = offset, bundle_of, bundles
        return None

    def arrow_into(self, key, chain):
        """The straight arrow to cut so key's track comes loose: the one into key, or out of it."""
        for i, (_, ki) in self.straight.items():
            if ki == key:
                return i
        for i, (ko, _) in self.straight.items():
            if ko == key:
                return i
        return next(i for i, (ko, ki) in self.straight.items() if ko in chain or ki in chain)

    def cells(self, chain):
        """What a track puts in each column: a card, a gap of a group, or its line passing by."""
        out = {}
        for a, b in zip(chain, chain[1:]):
            for c in range(self.key_col(a) + 1, self.key_col(b)):
                out[c] = ("line", None)
        for k in chain:
            out[self.key_col(k)] = (k[0], self.key_group(k))
        return out

    def clash(self, members, tracks, offset):
        """A straight arrow to give up if two tracks of one bundle crowd each other."""
        seen = {}
        for t in members:
            for c, item in self.cells(tracks[t]).items():
                row = offset[t]
                for row2, item2 in seen.get(c, []):
                    if too_close(row, item, row2, item2):
                        return self.arrow_near(tracks[t], c)
                seen.setdefault(c, []).append((row, item))
        return None

    def arrow_near(self, chain, col):
        """The straight arrow of a track nearest a column."""
        options = [i for i, (ko, ki) in self.straight.items() if ko in chain and ki in chain]
        return min(options, key=lambda i: min(abs(self.key_col(self.straight[i][0]) - col),
                                              abs(self.key_col(self.straight[i][1]) - col)))

    # --- 4. Rows: bundles around the critical path ------------------------------------------------

    def group_spans(self, rows):
        """Each group's rows in its column, from its label above to its padding below."""
        spans = {}
        for g in self.tree.groups:
            k = ("card", self.cards[g][0])
            top = rows[self.track_of[k]]
            spans.setdefault(self.col[g], []).append((top, top + 2 * len(self.cards[g]) - 2, g))
        return spans

    def fits(self, b, base, rows):
        """Whether bundle b fits at base, next to the bundles already placed."""
        mine = {t: base + self.offset[t] for t in self.bundles[b]}
        trial = dict(rows)
        trial.update(mine)
        spans = self.group_spans_for(trial)
        for t, row in mine.items():
            for c, item in self.cells(self.tracks[t]).items():
                for t2, row2 in rows.items():
                    cell = self.cells(self.tracks[t2]).get(c)
                    if cell and too_close(row, item, row2, cell):
                        return False
                for top, bottom, g in spans.get(c, []):
                    if item[1] != g and inside(row, item, top, bottom):
                        return False
        for t2, row2 in rows.items():                       # and theirs clear of my groups
            for c, item in self.cells(self.tracks[t2]).items():
                for top, bottom, g in spans.get(c, []):
                    if item[1] != g and self.bundle_of.get(self.track_of.get(("card", self.cards[g][0]))) == b \
                            and inside(row2, item, top, bottom):
                        return False
        return True

    def group_spans_for(self, rows):
        spans = {}
        for g in self.tree.groups:
            t = self.track_of[("card", self.cards[g][0])]
            if t in rows:
                top = rows[t]
                spans.setdefault(self.col[g], []).append((top, top + 2 * len(self.cards[g]) - 2, g))
        return spans

    def place(self):
        """The critical path's bundle on row 0; then each bundle, most connected first, where it
        fits nearest the rows it joins, keeping the drawing compact."""
        start = self.track_of[("card", self.tree.critical[0])] if self.tree.critical else 0
        first = self.bundle_of[start]
        rows = {t: self.offset[t] - self.offset[start] for t in self.bundles[first]}
        placed = {first}
        bent = [i for i in range(len(self.edges)) if i not in self.straight]

        def ends(i):
            a, b = self.edges[i]
            return self.end_key(a, i), self.end_key(b, i)

        while len(placed) < len(self.bundles):
            def links(b):
                n = 0
                for i in bent:
                    ka, kb = ends(i)
                    ba, bb = self.bundle_of[self.track_of[ka]], self.bundle_of[self.track_of[kb]]
                    n += (ba == b and bb in placed) or (bb == b and ba in placed)
                return n, len(self.bundles[b])
            b = max((b for b in range(len(self.bundles)) if b not in placed), key=links)
            targets = self.pull_targets(b, rows, bent, ends)          # (row it wants, my key)
            wishes = [r - self.offset[self.track_of[k]] for r, k in targets]
            ideal = round(sum(wishes) / len(wishes)) if wishes else 0
            lo = min(rows.values()) - 2 * len(self.bundles[b]) - 4
            hi = max(rows.values()) + 4
            best = None
            for base in range(lo - 40, hi + 40):
                if not self.fits(b, base, rows):
                    continue
                pull = sum(abs(base - w) for w in wishes)
                spread = max(max(rows.values()), base) - min(min(rows.values()), base)
                cost = pull + 0.5 * abs(base - ideal) + 0.3 * spread
                if best is None or cost < best[0]:
                    best = (cost, base)
            if best is None:
                fail("no room for a bundle of tracks; this tree is too big to lay out")
            for t in self.bundles[b]:
                rows[t] = best[1] + self.offset[t]
            placed.add(b)
        self.set_rows(rows)

    def set_rows(self, rows):
        self.rows = dict(rows)
        self.set_h({u: rows[self.track_of[("card", self.cards[u][0])]] for u in self.units})

    def set_h(self, h):
        """Put each unit's top card on a half row, and note where everything now is."""
        self.h = dict(h)
        self.card_boxes = {c: self.card_box(c) for c in self.tree.tasks}
        self.label_boxes = [self.label_box(g) for g in self.tree.groups]
        self.group_boxes = {g: self.group_box(g) for g in self.tree.groups}

    def route_all(self):
        """Route every arrow: the critical path first, then the straight ones, then the rest,
        shortest first."""
        t = self.tree
        self.routes = [None] * len(self.edges)
        self.slots = set()
        order = sorted(range(len(self.edges)), key=lambda i: (not self.spine[i], i not in self.straight,
                                                               self.col[t.unit(self.edges[i][1])]
                                                               - self.col[t.unit(self.edges[i][0])]))
        for i in order:
            self.reroute(i)

    def polish_bundles(self):
        """Move whole bundles while the drawing gets better: into free room, or in between others,
        pushing the bundles below down. Arrows that bend need room to go round cards, which
        placing the tracks didn't think of."""
        spine = self.bundle_of[self.track_of[("card", self.tree.critical[0])]] if self.tree.critical else None
        best, _ = self.score()
        for _ in range(4):
            improved = False
            for b in sorted(range(len(self.bundles)), key=lambda b: -len(self.bundles[b])):
                if b == spine:
                    continue
                choice = None
                for rows in self.moves_for(b):
                    change = {u: rows[self.track_of[("card", self.cards[u][0])]] for u in self.units}
                    change = {u: h for u, h in change.items() if h != self.h[u]}
                    score = self.try_change(change) if change else None
                    if score is not None and score < best - 1e-6:
                        best, choice = score, rows
                if choice:
                    self.set_rows(choice)
                    self.route_all()
                    best, _ = self.score()
                    improved = True
            if not improved:
                break

    # --- Polish: moves a person would make -------------------------------------------------------

    def legal(self, h, cols):
        """Whether nothing overlaps in the given columns with units at rows h."""
        for c in cols:
            spans = sorted((h[u] - 1, h[u] + 2 * len(self.cards[u]) - 1) for u in self.units if self.col[u] == c)
            if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
                return False
        return True

    def try_change(self, change):
        """The score with some units moved, re-routing only the arrows that could change; the
        drawing is put back as it was."""
        kept_h, kept_routes = dict(self.h), list(self.routes)
        h = {**self.h, **change}
        if not self.legal(h, {self.col[u] for u in change}):
            return None
        self.set_h(h)
        moved = set(change)
        boxes = [self.card_box(c) for u in moved for c in self.cards[u]]
        boxes += [self.group_box(u) for u in moved if u in self.tree.groups]
        boxes += [self.label_box(u) for u in moved if u in self.tree.groups]
        affected = {i for u in moved for i in self.incident[u]}
        for i, r in enumerate(self.routes):
            if i not in affected and any(hits(s, b) for s in zip(r[3], r[3][1:]) for b in boxes):
                affected.add(i)
        for i in affected:
            self.slots.difference_update(self.routes[i][4])
            self.routes[i] = None
        for i in sorted(affected, key=lambda i: (not self.spine[i], i)):
            self.reroute(i)
        score, _ = self.score()
        self.set_h(kept_h)
        self.routes = kept_routes
        self.slots = {sl for r in self.routes for sl in r[4]}
        return score

    def apply(self, change):
        self.set_h({**self.h, **change})
        self.route_all()

    def moves(self, u):
        """Rows worth trying for u: in line with what it's joined to, next to where it is, clear of
        everything; a swap with each unit of its column; and taking a unit's row, pushing it to
        its nearest free row."""
        rows = {self.h[u] + d for d in (-2, -1, 1, 2)}
        mine = [0] if u not in self.tree.groups else list(range(2 * len(self.cards[u]) - 1))
        for i in self.incident[u]:
            a, b = self.edges[i]
            other = b if self.tree.unit(a) == u else a
            for y in self.ports(other):                    # cards sit on half rows exactly
                for k in mine:
                    rows.add(round(y / HALF) - k)
        top = min(self.span(v)[0] for v in self.units)
        bottom = max(self.span(v)[1] for v in self.units)
        rows.update((top - 2 * len(self.cards[u]), bottom + 1))
        out = [{u: r} for r in sorted(rows) if r != self.h[u]]
        column = [v for v in self.units if v != u and self.col[v] == self.col[u]]
        out += [{u: self.h[v], v: self.h[u]} for v in column]
        for v in column:
            for d in range(2, 40):
                spot = next((self.h[v] + s * d for s in (1, -1)
                             if self.legal({**self.h, u: self.h[v], v: self.h[v] + s * d}, {self.col[u]})), None)
                if spot is not None:
                    out.append({u: self.h[v], v: spot})
                    break
        return out

    def repair(self):
        """First the arrows in trouble: of all the moves of their cards, and of the cards they run
        into, make the best one; again, while one helps."""
        best, _ = self.score()
        tries = 0
        for _ in range(6):
            bad = self.flagged()
            if not bad:
                break
            suspects = []
            for i in bad:
                a, b = self.edges[i]
                suspects += [self.tree.unit(a), self.tree.unit(b)]
                pts = self.routes[i][3]
                suspects += [self.unit_of[c] for c, box in self.card_boxes.items()
                             if any(hits(s, box) for s in zip(pts, pts[1:]))]
            choice = None
            for u in dict.fromkeys(suspects):
                for change in self.moves(u):
                    tries += 1
                    score = self.try_change(change)
                    if score is not None and score < best - 1e-6:
                        best, choice = score, change
            if choice is None:
                break
            self.apply(choice)
            best, _ = self.score()
        return tries

    def polish(self, budget=4000):
        """Move cards the way a person tidying the board would: first to clear the arrows in
        trouble, then card by card, keeping each move that makes the drawing better, until none
        does (or the budget of tries runs out)."""
        tries = self.repair()
        best, _ = self.score()
        while tries < budget:
            improved = False
            trouble = {u for i in self.flagged() for u in (self.tree.unit(self.edges[i][0]),
                                                            self.tree.unit(self.edges[i][1]))}
            for u in sorted(self.units, key=lambda u: (u not in trouble, str(u))):
                choice = None
                for change in self.moves(u):
                    tries += 1
                    score = self.try_change(change)
                    if score is not None and score < best - 1e-6:
                        best, choice = score, change
                    if tries >= budget:
                        break
                if choice:
                    self.apply(choice)
                    best, _ = self.score()
                    improved = True
                if tries >= budget:
                    break
            if not improved:
                break
        return tries

    def moves_for(self, b):
        """Rows to try for bundle b: every base where it fits as things are, and every base where
        it fits once the bundles from there down move down to make room."""
        first = self.bundles[b][0]
        current = self.rows[first] - self.offset[first]
        others = {t: r for t, r in self.rows.items() if self.bundle_of[t] != b}
        if not others:
            return []
        rel = [self.offset[t] for t in self.bundles[b]]
        height = max(rel) - min(rel) + 2 * max(len(self.cards[self.unit_of[k[1]]]) for t in self.bundles[b]
                                                for k in self.tracks[t] if k[0] == "card") + 2
        lo, hi = min(others.values()) - height - 2, max(others.values()) + 2
        tops = {}
        for t, r in others.items():
            tops.setdefault(self.bundle_of[t], []).append(r)
        out = []
        for base in range(lo, hi + 1):
            if base != current and self.fits(b, base, others):
                rows = dict(others)
                rows.update({t: base + self.offset[t] for t in self.bundles[b]})
                out.append(rows)
            # Push every bundle that starts at or below base down by b's height.
            cut = base + min(rel) - 1
            if any(min(rs) < cut <= max(rs) for rs in tops.values()):
                continue                                     # a bundle would be cut in two
            pushed = {t: r + height if min(tops[self.bundle_of[t]]) >= cut else r for t, r in others.items()}
            if pushed != others and self.fits(b, base, pushed):
                rows = dict(pushed)
                rows.update({t: base + self.offset[t] for t in self.bundles[b]})
                out.append(rows)
        return out

    def end_key(self, ref, i):
        """The key an arrow's end belongs to, for placing: a card, or a group's first card."""
        return ("card", ref) if ref not in self.tree.groups else ("card", self.cards[ref][0])

    def pull_targets(self, b, rows, bent, ends):
        out = []
        for i in bent:
            ka, kb = ends(i)
            for mine, other in ((ka, kb), (kb, ka)):
                tm, to = self.track_of[mine], self.track_of[other]
                if self.bundle_of[tm] == b and to in rows:
                    out.append((rows[to], mine))
        return out

    # --- The plan ---------------------------------------------------------------------------------

    def key(self):
        """The key, grouped, above the drawing's top left: a swatch for each status, the same on
        every board, and the critical path's orange arrow. The footer goes to its right."""
        t = self.tree
        rows = list(KEY)
        if t.critical:
            rows.append(("critical", "Critical path (longest sequence)"))
        top = -100 - KEY_ROW * len(rows)
        w, h = KEY_SWATCH
        ops, ids = [], []
        for k, (state, label) in enumerate(rows):
            y = top + k * KEY_ROW
            if state == "critical":
                ops.append({"op": "add", "type": "conn", "temp_id": "key-arrow", "from_pos": {"x": 0, "y": y + h // 2},
                            "to_pos": {"x": w, "y": y + h // 2}, "color": "orange", "to_endpoint": "arrow"})
                ids.append("key-arrow")
            else:
                ops.append({"op": "add", "type": "shape", "shape_type": "rect", "temp_id": f"key-{state}", "text": "",
                            "color": COLORS[state], "deco": "fill", "x": 0, "y": y, "width": w, "height": h})
                ids.append(f"key-{state}")
            ops.append({"op": "add", "type": "text", "temp_id": f"key-{state}-label", "text": label,
                        "x": w + 24, "y": y + 2, "width": 260, "text_align": "left"})
            ids.append(f"key-{state}-label")
        ops.append({"op": "group", "ids": ids})
        self.footer_at = {"x": w + 24 + 260 + 112, "y": top, "width": 503}
        return ops

    def plan(self):
        t = self.tree
        for g in t.groups:
            t.groups[g]["tasks"] = list(self.cards[g])
        lo = min(self.span(u)[0] for u in self.units) * HALF
        dy = -lo                                          # the drawing starts at y = 0
        ops = self.key()
        for g, spec in t.groups.items():
            x, y, w, h = self.group_box(g)
            ops.append({"op": "add", "type": "text", "text": spec["label"], "x": round(x),
                        "y": round(y + dy - LABEL), "width": round(w), "text_align": "center"})
            ops.append({"op": "add", "type": "shape", "shape_type": "rect", "temp_id": g, "text": "",
                        "color": "silver", "deco": "dashes", "x": round(x), "y": round(y + dy),
                        "width": round(w), "height": round(h)})
        for task, spec in t.tasks.items():
            x, y, w, h = self.card_box(task)
            op = {"op": "add", "type": "task", "temp_id": task, "title": spec["title"],
                  "color": COLORS[t.state[task]], "x": round(x), "y": round(y + dy), "width": w, "height": h}
            if spec.get("url"):                           # where the task lives, such as its Linear issue
                op["description"] = f"[{spec.get('ref') or 'Open the source'}]({spec['url']})"
            ops.append(op)
        # The critical path last: the board stacks objects in the order they're added. An arrow
        # with no clean route is red, for the agent to look at.
        flagged = set(self.flagged())
        for i in sorted(range(len(self.edges)), key=lambda i: (self.spine[i], i)):
            a, b = self.edges[i]
            from_rel, to_rel = self.routes[i][1], self.routes[i][2]
            op = {"op": "add", "type": "conn", "from_id": a, "to_id": b, "from_rel": from_rel,
                  "to_rel": to_rel, "to_endpoint": "arrow"}
            if i in flagged:
                op["color"] = "red"
            elif self.spine[i]:
                op["color"] = "orange"
            ops.append(op)
        return ops


# --- 3. Placing cards in layers: few crossings first, then straight arrows ------------------------

class Layers:
    """Rows for a grid's units the way Graphviz places them, in two steps.

    1. The order in each column, to cross as few arrows as it can: an arrow that skips columns
       gets a placeholder in each, and sweeps right and left move every unit to the median of
       its neighbours, then swaps and sifting (trying a unit at every place in its column) take
       whatever crossing is left. Several starting orders; the best wins.
    2. Rows, keeping that order: column by column, the exact rows that line up the most arrows
       (straight), then make the rest short. The critical path is pinned to row 0.
    """

    def __init__(self, grid):
        self.g = grid
        t = grid.tree
        self.col = dict(grid.col)
        self.size = {u: len(grid.cards[u]) for u in grid.units}
        self.links = []                      # (u, v, weight, offset in u, offset in v, edge)
        for i, (a, b) in enumerate(grid.edges):
            ua, ub = t.unit(a), t.unit(b)
            chain = [ua]
            for c in range(self.col[ua] + 1, self.col[ub]):
                d = ("~", i, c)
                self.col[d], self.size[d] = c, 0
                chain.append(d)
            chain.append(ub)
            weight = 3 if grid.spine[i] else 1
            offsets = [self.offset(a)] + [0] * (len(chain) - 2) + [self.offset(b)]
            for k in range(len(chain) - 1):
                self.links.append((chain[k], chain[k + 1], weight, offsets[k], offsets[k + 1], i))
        self.nodes = list(self.col)
        self.left = {n: [] for n in self.nodes}
        self.right = {n: [] for n in self.nodes}
        for u, v, w, ou, ov, i in self.links:
            self.right[u].append((v, w, ou, ov, i))
            self.left[v].append((u, w, ov, ou, i))
        self.columns = max(self.col.values()) + 1
        self.layers = self.order()
        self.sort_cards()
        self.rows = self.place()

    def offset(self, ref):
        """Where an arrow meets ref, in half rows from its unit's top card: a card's own row, or
        for a group the gap between its cards nearest its middle."""
        g = self.g
        if ref in g.tree.groups:
            k = len(g.cards[ref])
            return k - 1 if k % 2 == 0 else k - 2
        u = g.unit_of[ref]
        return 2 * g.cards[u].index(ref) if u in g.tree.groups else 0

    # --- 1. Order ---------------------------------------------------------------------------------

    def crossings(self, layers, cols=None):
        """Weighted pairs of arrows that cross between neighbouring columns."""
        total = 0
        pos = {n: i for layer in layers for i, n in enumerate(layer)}
        for c in range(self.columns - 1) if cols is None else cols:
            if c < 0 or c >= self.columns - 1:
                continue
            es = [(pos[u], pos[v], w) for u in layers[c] for v, w, _, _, _ in self.right[u]]
            for k, (a1, b1, w1) in enumerate(es):
                for a2, b2, w2 in es[k + 1:]:
                    if (a1 - a2) * (b1 - b2) < 0:
                        total += w1 * w2
        return total

    def order(self):
        g = self.g
        firsts = []
        seen = set()

        def visit(n, layers):                       # depth first, as Graphviz starts
            if n in seen:
                return
            seen.add(n)
            layers[self.col[n]].append(n)
            for v, *_ in self.right[n]:
                visit(v, layers)

        start = [[] for _ in range(self.columns)]
        roots = sorted(self.nodes, key=lambda n: (self.col[n], str(n) not in g.spine_units, str(n)))
        for n in roots:
            visit(n, start)
        firsts.append(start)
        rng = random.Random(0)
        for _ in range(6):                          # a few shuffled starts as well
            firsts.append([rng.sample(layer, len(layer)) for layer in start])
        best, best_cross = None, None
        for layers in firsts:
            layers = [list(layer) for layer in layers]
            current = self.crossings(layers)
            kept, stale = [list(x) for x in layers], 0
            for sweep in range(24):
                if sweep % 2 == 0:
                    for c in range(1, self.columns):
                        layers[c] = self.median(layers, c, layers[c - 1], self.left)
                else:
                    for c in range(self.columns - 2, -1, -1):
                        layers[c] = self.median(layers, c, layers[c + 1], self.right)
                self.transpose(layers)
                cross = self.crossings(layers)
                if cross < current:
                    current, kept, stale = cross, [list(x) for x in layers], 0
                else:
                    stale += 1
                    if stale >= 4:
                        break
            layers = kept
            self.sift(layers)
            cross = self.crossings(layers)
            if best is None or cross < best_cross:
                best, best_cross = layers, cross
        self.crossing_count = best_cross
        return best

    def median(self, layers, c, fixed, neighbours):
        pos = {n: i for i, n in enumerate(fixed)}
        keyed = []
        for i, n in enumerate(layers[c]):
            ps = sorted(pos[m] for m, *_ in neighbours[n] if m in pos)
            if ps:
                mid = len(ps) // 2
                keyed.append((ps[mid] if len(ps) % 2 else (ps[mid - 1] + ps[mid]) / 2, i, n))
            else:
                keyed.append((None, i, n))
        movable = iter(sorted((k, i, n) for k, i, n in keyed if k is not None))
        return [n if k is None else next(movable)[2] for k, i, n in keyed]

    def transpose(self, layers):
        for _ in range(8):
            better = False
            for c in range(self.columns):
                for i in range(len(layers[c]) - 1):
                    near = [c - 1, c]
                    before = self.crossings(layers, near)
                    layers[c][i], layers[c][i + 1] = layers[c][i + 1], layers[c][i]
                    if self.crossings(layers, near) < before:
                        better = True
                    else:
                        layers[c][i], layers[c][i + 1] = layers[c][i + 1], layers[c][i]
            if not better:
                return

    def sift(self, layers):
        """Try each unit at every place in its column; keep the place that crosses least."""
        for _ in range(2):
            for c in range(self.columns):
                for n in list(layers[c]):
                    near = [c - 1, c]
                    layers[c].remove(n)
                    best = None
                    for k in range(len(layers[c]) + 1):
                        layers[c].insert(k, n)
                        cross = self.crossings(layers, near)
                        if best is None or cross < best[0]:
                            best = (cross, k)
                        layers[c].pop(k)
                    layers[c].insert(best[1], n)

    def sort_cards(self):
        """A group's cards in the order of what they're joined to, so their arrows don't cross."""
        g = self.g
        pos = {n: i for layer in self.layers for i, n in enumerate(layer)}
        for grp in g.tree.groups:
            def key(card):
                ns = [pos[m] for a, b in g.edges for m, mine in ((g.tree.unit(b), a), (g.tree.unit(a), b))
                      if mine == card and m in pos]
                return sum(ns) / len(ns) if ns else float("inf")
            g.cards[grp].sort(key=key)
        # Offsets into groups changed with the order of their cards.
        self.links = [(u, v, w, self.port_of(i, u, True) if u in g.units else ou,
                       self.port_of(i, v, False) if v in g.units else ov, i)
                      for u, v, w, ou, ov, i in self.links]
        self.left = {n: [] for n in self.nodes}
        self.right = {n: [] for n in self.nodes}
        for u, v, w, ou, ov, i in self.links:
            self.right[u].append((v, w, ou, ov, i))
            self.left[v].append((u, w, ov, ou, i))

    def port_of(self, i, unit, start):
        a, b = self.g.edges[i]
        return self.offset(a if start else b)

    # --- 2. Rows ----------------------------------------------------------------------------------

    def gap(self, upper, lower):
        """The least half rows between two neighbours in a column, top card to top card."""
        bottom = 2 * (self.size[upper] - 1) if self.size[upper] else 0
        if self.size[upper] == 0 and self.size[lower] == 0:
            need = 1                                  # two passing arrows
        elif self.size[upper] == 0:
            need = 2 if lower in self.g.tree.groups else 1   # an arrow above a group: its label
        elif self.size[lower] == 0:
            need = 1
        else:
            need = 2
        return bottom + need

    def place(self):
        g = self.g
        spine = {u for u in g.units if u in g.spine_units}
        spine |= {d for u, v, w, ou, ov, i in self.links if g.spine[i] for d in (u, v) if isinstance(d, tuple)}
        pin = {}
        for n in spine:
            if n in g.units:
                pin[n] = -min((2 * g.cards[n].index(c) for c in g.cards[n] if c in g.tree.critical), default=0)
            else:
                pin[n] = 0
        rows = {}
        for c in range(self.columns):                 # a first guess: stacked, the spine on 0
            r = 0
            layer = self.layers[c]
            k = next((i for i, n in enumerate(layer) if n in pin), None)
            if k is not None:
                rows[layer[k]] = pin[layer[k]]
                for i in range(k - 1, -1, -1):
                    rows[layer[i]] = rows[layer[i + 1]] - self.gap(layer[i], layer[i + 1])
                for i in range(k + 1, len(layer)):
                    rows[layer[i]] = rows[layer[i - 1]] + self.gap(layer[i - 1], layer[i])
            else:
                for k, n in enumerate(layer):
                    if k:
                        r += self.gap(layer[k - 1], n)
                    rows[n] = r
        best = (self.cost(rows), dict(rows))
        for sweep in range(12):
            cols = range(self.columns) if sweep % 2 == 0 else range(self.columns - 1, -1, -1)
            for c in cols:
                self.column(c, rows, pin, sweep % 3)
            cost = self.cost(rows)
            if cost < best[0]:
                best = (cost, dict(rows))
        return {u: r for u, r in best[1].items() if u in g.units}

    def pull(self, n, side, rows):
        """Where n's arrows want it, as (row for n's top, weight) pairs."""
        out = []
        sides = (self.left, self.right) if side == 0 else (self.left,) if side == 1 else (self.right,)
        for nb in sides:
            for m, _, mine, theirs, i in nb[n]:
                if m in rows:
                    weight = 1000 if self.g.spine[i] else 10 if isinstance(m, tuple) or isinstance(n, tuple) else 3
                    out.append((rows[m] + theirs - mine, weight))
        return out

    def column(self, c, rows, pin, side):
        """The exact rows for one column, its order kept: as many arrows lined up as can be."""
        layer = self.layers[c]
        wants = {n: self.pull(n, side, rows) for n in layer}

        def cost(n, r):
            if n in pin:
                return 0 if r == pin[n] else 10 ** 9
            return sum(w * (0 if r == want else 1 + 0.05 * abs(r - want)) for want, w in wants[n])

        known = [want for n in layer for want, _ in wants[n]] + [rows[n] for n in layer]
        total = sum(self.gap(a, b) for a, b in zip(layer, layer[1:])) + 4
        lo, hi = int(min(known)) - total, int(max(known)) + total
        span = range(lo, hi + 1)
        table = [{r: (cost(layer[0], r), None) for r in span}]
        for k in range(1, len(layer)):
            need = self.gap(layer[k - 1], layer[k])
            prev, row, run, arg = table[-1], {}, float("inf"), None
            for r in span:
                q = r - need
                if q in prev and prev[q][0] < run:
                    run, arg = prev[q][0], q
                if arg is not None:
                    row[r] = (run + cost(layer[k], r), arg)
            table.append(row)
        r = min(table[-1], key=lambda x: (table[-1][x][0], abs(x)))
        for k in range(len(layer) - 1, -1, -1):
            rows[layer[k]] = r
            r = table[k][r][1]

    def cost(self, rows):
        """Arrows not lined up, then their length, then the height."""
        bent = length = 0
        for u, v, w, ou, ov, _ in self.links:
            d = abs((rows[u] + ou) - (rows[v] + ov))
            bent += w * (d > 0)
            length += w * d
        height = max(rows.values()) - min(rows.values())
        return 100 * bent + length + 0.5 * height


def route(elbows, start, end, points, slots):
    """A route, with its pieces, bounding box and length worked out once:
    (elbows, from anchor, to anchor, points, slots, pieces, box, length)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    length = sum(abs(x2 - x1) + abs(y2 - y1) for (x1, y1), (x2, y2) in zip(points, points[1:]))
    return (elbows, start, end, points, slots, tuple(zip(points, points[1:])), (min(xs), min(ys), max(xs), max(ys)),
            length)


def near(box, other, margin=0):
    """Whether two routes' boxes, (x1, y1, x2, y2), come within margin of each other."""
    return box[0] - margin <= other[2] and other[0] - margin <= box[2] and \
        box[1] - margin <= other[3] and other[1] - margin <= box[3]


def touches(box, rect):
    """Whether a route's box, (x1, y1, x2, y2), meets a card's or a label's, (x, y, width, height)."""
    return box[0] <= rect[0] + rect[2] and rect[0] <= box[2] and box[1] <= rect[1] + rect[3] and rect[1] <= box[3]


def hits(seg, box):
    (x1, y1), (x2, y2) = seg
    bx, by, bw, bh = box
    return min(x1, x2) < bx + bw - 1 and max(x1, x2) > bx + 1 and min(y1, y2) < by + bh - 1 and max(y1, y2) > by + 1


def crosses(s1, s2):
    v1, v2 = s1[0][0] == s1[1][0], s2[0][0] == s2[1][0]
    if v1 == v2:
        return False
    h, v = (s2, s1) if v1 else (s1, s2)
    return (min(h[0][0], h[1][0]) < v[0][0] < max(h[0][0], h[1][0])
            and min(v[0][1], v[1][1]) < h[0][1] < max(v[0][1], v[1][1]))


def overlap(s1, s2):
    """Two segments that read as one line: along the same line, or within a few pixels of it,
    overlapping or end to end with a short gap, so the eye runs from one into the other."""
    v1, v2 = s1[0][0] == s1[1][0], s2[0][0] == s2[1][0]
    if v1 != v2:
        return any(p == q for p in s1 for q in s2)       # a shared corner
    k = 0 if v1 else 1
    if abs(s1[0][k] - s2[0][k]) >= 12:
        return False
    lo = max(min(s1[0][1 - k], s1[1][1 - k]), min(s2[0][1 - k], s2[1][1 - k]))
    hi = min(max(s1[0][1 - k], s1[1][1 - k]), max(s2[0][1 - k], s2[1][1 - k]))
    return hi - lo > -24


def too_close(row, item, row2, item2):
    """Two things in one column too close: cards need a row between them, lines and gaps a half."""
    if item[0] == "card" and item2[0] == "card":
        return abs(row - row2) < 2
    return row == row2


def inside(row, item, top, bottom):
    """Whether something of another group sits in a group's rows: its cards from top to bottom,
    with its label above, and room below for a card."""
    if item[0] == "card":
        return top - 2 < row < bottom + 2
    return top - 2 < row < bottom + 1


def layout(path, strategy=None):
    """Lay the tree out in layers (or the way asked for). If an arrow is still in trouble, try
    tracks as well, which is slower, and keep the cleaner drawing."""
    tree = Tree(load_tree(path))
    tried = {}
    for name in [strategy] if strategy else ["layers", "tracks"]:
        if name == "tracks" and not strategy and not tried["layers"][1].flagged():
            break                                        # layers drew it cleanly: no need
        groups = {g: list(spec["tasks"]) for g, spec in tree.groups.items()}
        grid = Grid(tree, name)
        grid.polish()
        tried[name] = (grid.score(), grid, {g: list(spec["tasks"]) for g, spec in tree.groups.items()})
        for g, cards in groups.items():                  # the next strategy starts afresh
            tree.groups[g]["tasks"] = cards
    name = min(tried, key=lambda n: tried[n][0][0])
    (_, counts), grid, cards = tried[name]
    for g, order in cards.items():
        tree.groups[g]["tasks"] = order
    names = lambda es: [list(e) for e in es]  # noqa: E731
    return {
        "strategy": name,
        "tried": {n: dict(v[0][1], score=round(v[0][0], 1)) for n, v in tried.items()},
        "critical_path": [tree.tasks[t]["title"] for t in tree.critical],
        "critical_ties": tree.ties,
        "merged": names(tree.merged),
        "dropped": names(tree.dropped),
        "columns": max(grid.col.values()) + 1,
        "arrows": len(tree.edges),
        "straight": sum(1 for r in grid.routes if r[0] == 0),
        **counts,
        "flagged": [list(grid.edges[i]) for i in grid.flagged()],
        "ops": grid.plan(),
        "footer_at": grid.footer_at,
    }


def start(folder):
    """Note when the run began, so the footer can say how long it took."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    run = Path(folder) / "run.json"
    if run.exists():
        print(f"{run} exists: picking up the run that started then.")
        return
    run.write_text(json.dumps({"started": time.time()}) + "\n")
    print(f"Started a run in {folder}.")


def footer(folder, plan_path):
    """The footer's edit operation: how long the run took, and how to get the skill. The empty
    paragraph (a non-breaking space) keeps a line between the two: Whimsical drops blank lines."""
    try:
        run = json.loads((Path(folder) / "run.json").read_text())
        plan = json.loads(Path(plan_path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"can't read the run or the plan: {error}; run `start` first, and `layout` before this")
    seconds = max(1, round(time.time() - run["started"]))
    text = (f"Generated in **{seconds:,}** second{'s' if seconds != 1 else ''}, using the [{SKILL}]({SKILL_URL}) skill."
            f"\n\n\u00a0\n\nTry it\n\n```\nnpx skills add WhimsicalCode/skills --skill {SKILL}\n```")
    at = plan["footer_at"]
    return {"op": "add", "type": "text", "text": text, "x": at["x"], "y": at["y"], "width": at["width"],
            "text_align": "left"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="note when the run began, in its folder")
    p.add_argument("folder")
    p = sub.add_parser("footer", help="print the footer to add last: how long it took, how to get the skill")
    p.add_argument("folder")
    p.add_argument("plan")
    p = sub.add_parser("layout", help="lay out a tree.json and print the plan")
    p.add_argument("tree")
    p.add_argument("--strategy", choices=("layers", "tracks"), help="only this way (default: both, the better)")
    p.add_argument("--out", help="write the plan here instead of printing it")
    args = parser.parse_args()
    if args.command == "start":
        start(args.folder)
        return
    if args.command == "footer":
        print(json.dumps(footer(args.folder, args.plan), ensure_ascii=False))
        return
    plan = layout(args.tree, args.strategy)
    text = json.dumps(plan, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(json.dumps({k: v for k, v in plan.items() if k != "ops"}, indent=1, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()

