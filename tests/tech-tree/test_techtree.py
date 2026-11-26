import json

import pytest
import techtree
from conftest import FIXTURES, run_script, write_tree

# ---------------------------------------------------------------- the tree


def tree_of(tmp_path, tasks, edges=(), groups=None):
    return techtree.Tree(techtree.load_tree(write_tree(tmp_path, tasks, edges, groups)))


@pytest.mark.parametrize("tasks,edges,groups,message", [
    ({"a": "todo"}, [("a", "z")], None, "doesn't join two tasks or groups"),
    ({"a": "todo"}, [("a", "a")], None, "to itself"),
    ({"a": "todo", "b": "todo"}, [], {"g": {"label": "G", "tasks": ["a"]}}, "at least two tasks"),
    ({"a": "todo", "b": "todo"}, [], {"g": {"label": "G", "tasks": ["a", "x"]}}, "isn't a task"),
    ({"a": "nearly"}, [], None, "use todo, doing or done"),
])
def test_bad_trees_fail_with_a_reason(tmp_path, tasks, edges, groups, message):
    path = write_tree(tmp_path, tasks, edges, groups)
    with pytest.raises(SystemExit, match=message):
        techtree.Tree(techtree.load_tree(path))


def test_a_loop_is_named(tmp_path):
    with pytest.raises(SystemExit, match="a -> b -> c -> a"):
        tree_of(tmp_path, {"a": "todo", "b": "todo", "c": "todo"}, [("a", "b"), ("b", "c"), ("c", "a")])


def test_cards_of_one_group_cant_need_each_other(tmp_path):
    with pytest.raises(SystemExit, match="same group"):
        tree_of(tmp_path, {"a": "todo", "b": "todo"}, [("a", "b")], {"g": {"label": "G", "tasks": ["a", "b"]}})


def test_arrows_to_every_card_of_a_group_become_one(tmp_path):
    t = tree_of(tmp_path, {"x": "todo", "a": "todo", "b": "todo", "y": "todo"},
                [("x", "a"), ("x", "b"), ("a", "y"), ("b", "y")], {"g": {"label": "G", "tasks": ["a", "b"]}})
    assert sorted(t.edges) == [("g", "y"), ("x", "g")]
    assert sorted(t.merged) == [("g", "y"), ("x", "g")]


def test_an_arrow_another_path_implies_is_dropped(tmp_path):
    t = tree_of(tmp_path, {"a": "todo", "b": "todo", "c": "todo"}, [("a", "b"), ("b", "c"), ("a", "c")])
    assert sorted(t.edges) == [("a", "b"), ("b", "c")]
    assert t.dropped == [("a", "c")]


def test_status_start_now_needs_everything_before_done(tmp_path):
    t = tree_of(tmp_path, {"a": "done", "b": "todo", "c": "todo", "d": "doing"}, [("a", "b"), ("b", "c")])
    assert t.state == {"a": "done", "b": "ready", "c": "waiting", "d": "doing"}


def test_the_critical_path_is_the_longest_unfinished_chain(tmp_path):
    t = tree_of(tmp_path, {"a": "done", "b": "todo", "c": "todo", "d": "todo", "e": "todo"},
                [("a", "b"), ("b", "c"), ("c", "d"), ("a", "e")])
    assert t.critical == ["b", "c", "d"]
    assert t.ties == 1


def test_tied_critical_paths_are_counted(tmp_path):
    t = tree_of(tmp_path, {"a": "todo", "b": "todo", "c": "todo", "d": "todo"},
                [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert len(t.critical) == 3
    assert t.ties == 2


# ---------------------------------------------------------------- columns


def test_network_simplex_keeps_arrows_short():
    # a feeds d directly and through b and c: d can't move, but e, which only feeds d, sits just before it.
    nodes = ["a", "b", "c", "d", "e"]
    edges = {("a", "b"): 1, ("b", "c"): 1, ("c", "d"): 1, ("a", "d"): 1, ("e", "d"): 1}
    rank = techtree.rank_nodes(nodes, edges)
    assert [rank[n] for n in "abcd"] == [0, 1, 2, 3]
    assert rank["e"] == 2


def test_separate_trees_each_start_at_column_zero():
    rank = techtree.rank_nodes(["a", "b", "x", "y", "z"], {("a", "b"): 1, ("x", "y"): 1, ("y", "z"): 1})
    assert rank["a"] == 0 and rank["x"] == 0 and rank["b"] == 1 and rank["z"] == 2


# ---------------------------------------------------------------- arrows


def test_crossing_and_overlap():
    across = ((0, 5), (10, 5))
    down = ((5, 0), (5, 10))
    assert techtree.crosses(across, down)
    assert not techtree.crosses(across, ((20, 0), (20, 10)))
    assert techtree.overlap(across, ((8, 6), (20, 6)))          # along the same line
    assert techtree.overlap(across, ((20, 5), (30, 5)))         # end to end, the eye runs on
    assert not techtree.overlap(across, ((0, 30), (10, 30)))    # parallel, far enough apart


def test_routes_are_shapes_whimsical_draws(tmp_path):
    t = tree_of(tmp_path, {"a": "todo", "b": "todo", "c": "todo", "d": "todo"}, [("a", "b"), ("c", "d"), ("a", "d")])
    grid = techtree.Grid(t, "layers")
    for i in range(len(grid.edges)):
        for elbows, start, end, points, *_ in grid.candidates(i):
            assert len(points) - 2 == elbows
            assert start["a"] in "xy" and end["a"] in "xy"
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                assert x1 == x2 or y1 == y2, "every piece runs across or down"


# ---------------------------------------------------------------- example trees


@pytest.mark.parametrize("name,hops,elbows", [("carbonara", 0, 7), ("analytics", 5, 20), ("offsite", 5, 20)])
def test_fixture_trees_stay_at_least_this_clean(plans, name, hops, elbows):
    plan = plans[name]
    assert plan["flagged"] == []
    assert plan["through_cards"] == 0
    assert plan["overlaps"] == 0
    assert plan["hops"] <= hops
    assert plan["elbows"] <= elbows


@pytest.mark.parametrize("name", ["carbonara", "analytics", "offsite"])
def test_the_plan_draws_every_card_once_and_every_arrow(plans, name):
    tree = json.loads((FIXTURES / f"{name}.json").read_text())
    plan = plans[name]
    cards = [op for op in plan["ops"] if op.get("type") == "task"]
    assert sorted(op["temp_id"] for op in cards) == sorted(tree["tasks"])
    ids = {op.get("temp_id") for op in plan["ops"] if op["op"] == "add"}
    arrows = [op for op in plan["ops"] if op.get("type") == "conn" and "from_id" in op]
    assert len(arrows) == plan["arrows"]
    assert all(op["from_id"] in ids and op["to_id"] in ids for op in arrows)
    boxes = [(op["x"], op["y"], op["width"], op["height"]) for op in cards]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            apart = a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
            assert apart, f"cards overlap: {a} {b}"


@pytest.mark.parametrize("name", ["carbonara", "analytics", "offsite"])
def test_the_critical_path_is_orange_and_drawn_last(plans, name):
    arrows = [op for op in plans[name]["ops"] if op.get("type") == "conn" and "from_id" in op]
    orange = [i for i, op in enumerate(arrows) if op.get("color") == "orange"]
    assert orange, "the critical path has arrows"
    assert orange == list(range(len(arrows) - len(orange), len(arrows))), "on top of the others"


def test_the_key_is_grouped_and_lists_every_status(plans):
    ops = plans["analytics"]["ops"]
    labels = [op["text"] for op in ops if str(op.get("temp_id", "")).endswith("-label")]
    assert labels == ["Start now", "In progress", "Waiting", "Done", "Critical path (longest sequence)"]
    group = next(op for op in ops if op["op"] == "group")
    assert len(group["ids"]) == 2 * len(labels)


def test_the_same_tree_always_gets_the_same_plan():
    first = techtree.layout(FIXTURES / "carbonara.json")
    second = techtree.layout(FIXTURES / "carbonara.json")
    assert first["ops"] == second["ops"]


# ---------------------------------------------------------------- the commands


def test_start_layout_and_footer(tmp_path):
    folder = tmp_path / "tech-trees" / "acme"
    run_script("start", folder, cwd=tmp_path)
    assert json.loads((folder / "run.json").read_text())["started"] > 0
    again = run_script("start", folder, cwd=tmp_path)
    assert "picking up" in again.stdout
    tree = write_tree(folder, {"a": "done", "b": "todo"}, [("a", "b")])
    summary = json.loads(run_script("layout", tree, "--out", folder / "plan.json", cwd=tmp_path).stdout)
    assert summary["arrows"] == 1 and "ops" not in summary
    footer = json.loads(run_script("footer", folder, folder / "plan.json", cwd=tmp_path).stdout)
    assert footer["type"] == "text"
    assert footer["text"].startswith("Generated in **")
    assert "[tech-tree](https://whimsical.com/skills/tech-tree)" in footer["text"]
    assert "\n\n\u00a0\n\nTry it\n\n```\nnpx skills add WhimsicalCode/skills --skill tech-tree\n```" in footer["text"]


def test_footer_without_start_says_what_to_do(tmp_path):
    result = run_script("footer", tmp_path, tmp_path / "plan.json", cwd=tmp_path, check=False)
    assert result.returncode != 0
    assert "run `start` first" in result.stderr


def test_the_tracks_fallback_draws_cleanly_too():
    plan = techtree.layout(FIXTURES / "carbonara.json", "tracks")
    assert plan["strategy"] == "tracks"
    assert plan["flagged"] == [] and plan["through_cards"] == 0 and plan["overlaps"] == 0


def test_a_task_with_a_url_links_its_card_to_the_source(tmp_path):
    path = write_tree(tmp_path, {"a": "todo", "b": "todo"}, [("a", "b")])
    tree = json.loads(path.read_text())
    tree["tasks"]["a"].update(url="https://linear.app/acme/issue/ENG-142", ref="ENG-142")
    path.write_text(json.dumps(tree))
    cards = {op["temp_id"]: op for op in techtree.layout(path)["ops"] if op.get("type") == "task"}
    assert cards["a"]["description"] == "[ENG-142](https://linear.app/acme/issue/ENG-142)"
    assert "description" not in cards["b"]


def test_a_url_must_be_an_address(tmp_path):
    path = write_tree(tmp_path, {"a": "todo"})
    tree = json.loads(path.read_text())
    tree["tasks"]["a"]["url"] = "linear.app/acme/issue/ENG-142"
    path.write_text(json.dumps(tree))
    with pytest.raises(SystemExit, match="https://"):
        techtree.load_tree(path)
