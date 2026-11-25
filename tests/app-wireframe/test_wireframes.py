import json
from pathlib import Path

import pytest
import wireframes as wf
from conftest import run_script
from PIL import Image


def cli(*args, check=True):
    return run_script("wireframes.py", *args, check=check)


def text(t, size="m", **style):
    return ["text", {"text": t, "font-size": size, **({"layout/style": style} if style else {})}]


def col(*children, **attrs):
    return ["div", {"layout/style": {"flex-direction": "column"}, **attrs}, *children]


def row(*children, **attrs):
    return ["div", {"layout/style": {"flex-direction": "row"}, **attrs}, *children]


def errors(layout):
    return wf.lint_layout(layout).errors


# ---------------------------------------------------------------- draft checks

def test_valid_card_layout_passes():
    card = col(
        ["w-shape", {"color": "light-gray", "deco": "fill", "layout/style": {"height": 80, "margin": {"bottom": -80}}}],
        col(text("**Title**"), row(text("Meta", "s", flex=1),
                                   ["icon", {"icon-name": "favorite", "deco": "outline", "color": "red",
                                             "layout/style": {"width": 20, "height": 20}}])),
        group=True,
    )
    lint = wf.lint_layout(col(card, ["div", {"layout/style": {"flex-direction": "row", "margin": {"top": -8}}},
                                     text("Badge", flex=1)]))
    assert (lint.errors, lint.warnings) == ([], [])
    assert lint.groups == {"$/0": [0, 1, 2, 3]}
    assert [leaf["tag"] for leaf in lint.leaves] == ["w-shape", "text", "text", "icon", "text"]


def test_groups_nest_and_count_inner_groups_as_members():
    lint = wf.lint_layout(col(col(col(text("a"), text("b"), group=True), text("c"), group=True)))
    assert lint.errors == []
    assert lint.groups == {"$/0": ["$/0/0", 2], "$/0/0": [0, 1]}


def test_tabs_take_item_objects_with_icons():
    tabs = ["w-h-tabs", {"items": ["Home", {"text": "Search", "icon-name": "zoom-2", "selected": True}]}]
    assert errors(col(tabs)) == []


@pytest.mark.parametrize("layout, fragment", [
    (["div", {"layout/style": {"margin": {"top": 4}, "flex-direction": "column"}}], "root div can't take margin"),
    (["div", {}], "flex-direction explicitly"),
    (col(["w-shape", {}, text("x")]), "can't have children"),
    (col(["w-image", {}]), "unknown tag"),
    (col(["icon", {"icon-name": "favorite", "deco": "multicolor", "color": "red",
                   "layout/style": {"width": 20, "height": 20}}]), "multicolor icon can't take color"),
    (col(["icon", {"icon-name": "favorite", "deco": "outline", "wf/color": "red",
                   "layout/style": {"width": 20, "height": 20}}]), "wf/color is gone"),
    (col(["icon", {"icon-name": "favorite", "layout/style": {"width": 20, "height": 20}}]), "deco: outline"),
    (col(["icon", {"icon-name": "favorite", "deco": "outline"}]), "width and height"),
    (col(["w-icon", {"icon-name": "phone"}]), "draws something else"),
    (col(["w-icon", {"icon-name": "notification"}]), "isn't in the icon set"),
    (col(["w-dropdown", {"items": [{"text": "Home"}]}]), "must be a string"),
    (col(["w-h-tabs", {"items": [{"label": "Home"}]}]), "takes text (required)"),
    (col(["w-toggle", {}]), "w-toggle state"),
    (col(["w-button", {"text": "Go", "size": "m", "font-size": "s"}]), "not both"),
    (col(["w-shape", {"color": "teal"}]), "isn't a palette color"),
    (col(["w-stars", {"pos": 4.5}]), "pos must be between 0 and 1"),
    (col(col(text("a"), **{"wf/group": "card"})), "wf/group is gone"),
    (col(col(text("a"), group=True)), "at least 2 elements"),
    (col(col(text("a"), text("b"), group="yes")), "true or false"),
])
def test_check_catches_layouts_that_render_badly(layout, fragment):
    assert any(fragment in message for message in errors(layout)), errors(layout)


def test_plain_space_after_marker_is_fine():
    assert errors(col(text("**Almost gone.** This"))) == []


def test_warns_on_explicit_text_height():
    assert any("measures text" in w for w in wf.lint_layout(col(text("x", height=24))).warnings)


def test_warns_on_heavy_placeholders_and_outlined_cards():
    lint = wf.lint_layout(col(
        ["w-shape", {"color": "silver", "icon-name": "image", "layout/style": {"height": 100}}],
        ["w-shape", {"color": "white", "deco": "outline", "layout/style": {"width": 360, "height": 120}}]))
    assert any("looks heavy" in w for w in lint.warnings)
    assert any("outlined card" in w for w in lint.warnings)


def test_strip_markdown_matches_rendered_text():
    assert wf.strip_markdown("~~£2.49~~\u00a0£0 fee") == "£2.49 £0 fee"
    assert wf.strip_markdown("**Almost gone.**\u00a0This") == "Almost gone. This"


def test_check_command_exit_code(tmp_path):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(col(text("Hello"))))
    bad.write_text(json.dumps(col(["w-image", {}])))
    assert cli("check", good).returncode == 0
    assert cli("check", bad, check=False).returncode == 1


# ---------------------------------------------------------------- ledger

def test_init_reads_selection_and_refuses_reinit(make_run):
    run = make_run()
    state = json.loads((run / "run.json").read_text())
    assert state["app"] == "Demo"
    assert [s["title"] for s in state["screens"]] == ["01 Screen 0", "02 Screen 1"]
    assert state["screens"][1]["mobbin_url"].endswith("00000001")
    assert cli("init", run, check=False).returncode != 0


def test_init_accepts_a_plain_screenshot_folder(tmp_path):
    shots = tmp_path / "shots"
    shots.mkdir()
    Image.new("RGB", (1179, 2556), "white").save(shots / "checkout.png")
    cli("init", tmp_path / "Checkout", "--screenshots", shots, "--app", "My app")
    state = json.loads((tmp_path / "Checkout" / "run.json").read_text())
    assert state["app"] == "My app"
    assert state["screens"][0]["label"] == "checkout" and state["screens"][0]["mobbin_url"] is None


def test_set_refuses_second_frame(make_run):
    run = make_run()
    cli("set", run, "01", "frame_id=AAA", "status=rendered", "--bump", "renders")
    screen = json.loads((run / "run.json").read_text())["screens"][0]
    assert (screen["frame_id"], screen["status"], screen["renders"]) == ("AAA", "rendered", 1)
    assert cli("set", run, "01", "frame_id=BBB", check=False).returncode != 0


def test_icon_check_board_is_separate_from_the_wireframe_board(make_run):
    run = make_run()
    cli("board", run, "--id", "BOARD")
    assert cli("board", run, "--id", "BOARD", "--swatch-board", "BOARD", check=False).returncode != 0
    cli("board", run, "--id", "BOARD", "--swatch-board", "SCRATCH")
    assert json.loads((run / "run.json").read_text())["swatch_board_id"] == "SCRATCH"


# ---------------------------------------------------------------- render and links

@pytest.fixture
def prepared_run(make_run):
    run = make_run()
    cli("board", run, "--id", "BOARD")
    draft = col(
        col(["w-shape", {"color": "light-gray", "deco": "fill",
                         "layout/style": {"height": 40, "margin": {"bottom": -40}}}],
            row(text("Card, title", flex=1),
                ["icon", {"icon-name": "favorite", "deco": "outline", "color": "red",
                          "layout/style": {"width": 20, "height": 20}}]),
            group=True),
        text("Footer"),
    )
    (run / "drafts" / "01.json").write_text(json.dumps(draft))
    return run


def test_prepare_prints_the_create_call_then_the_repair_call(prepared_run):
    first = json.loads(cli("prepare", prepared_run, "01").stdout)
    assert first["tool"] == "add_board_content"
    arguments = first["arguments"]
    assert (arguments["board_id"], arguments["title"], arguments["x"], arguments["y"]) == ("BOARD", "01 Screen 0",
                                                                                           216, 446)
    assert arguments["data"]["layout"] == json.loads((prepared_run / "drafts" / "01.json").read_text())
    cli("set", prepared_run, "01", "frame_id=FRAME")
    repair = json.loads(cli("prepare", prepared_run, "01").stdout)
    assert repair["tool"] == "wireframe_edit" and repair["arguments"]["target_id"] == "FRAME"


def test_prepare_places_frames_on_the_board_grid(make_run):
    run = make_run(sizes=[(1179, 2556)] * 7)
    cli("board", run, "--id", "BOARD")
    (run / "drafts" / "07.json").write_text(json.dumps(col(text("x"))))
    arguments = json.loads(cli("prepare", run, "07").stdout)["arguments"]
    assert (arguments["x"], arguments["y"]) == (wf.COLUMN_PITCH + 216, wf.ROW_PITCH + 446)


def test_links_go_under_each_frame(prepared_run, tmp_path):
    cli("set", prepared_run, "01", "frame_id=FRAME")
    (tmp_path / "f.txt").write_text("type,id,parentId,x,y,width,height,color,text\n"
                                    "frame,FRAME,,100,200,432,892,White,01 Screen 0\n")
    ops = json.loads(cli("links", prepared_run, tmp_path / "f.txt").stdout)["operations"]
    assert ops == [{"op": "add", "type": "link", "url": "https://mobbin.com/screens/00000000",
                    "text": "See screen on Mobbin.com", "x": 100.0, "y": 1112.0, "temp_id": "link01"}]


# ---------------------------------------------------------------- icons and grid

def test_icon_search_prefers_verified_names_and_hides_cloud_vendor_icons():
    names = [r["name"] for r in wf.search_icons("search")]
    assert names[0] == "zoom-2"
    assert not any(n.startswith(("azure-", "aws-")) for n in names)
    assert any("close" in c for r in wf.search_icons("close") for c in r["concepts"])


def test_icons_records_checked_names_and_refuses_misleading_ones(make_run):
    run = make_run()
    undescribed = next(n for n in wf.icon_index()["names"]
                       if n not in wf.icon_index()["descriptions"] and n not in wf.VERIFIED_ICONS)
    cli("icons", run, undescribed, "globe")
    assert json.loads((run / "run.json").read_text())["icons_checked"] == sorted([undescribed, "globe"])
    assert cli("icons", run, "phone", check=False).returncode != 0
    draft = col(["icon", {"icon-name": undescribed, "deco": "outline", "layout/style": {"width": 20, "height": 20}}])
    assert not any("no description" in w for w in wf.lint_layout(draft, [undescribed]).warnings)
    assert any("no description" in w for w in wf.lint_layout(draft).warnings)


def test_swatch_is_a_valid_layout():
    lint = wf.lint_layout(json.loads(cli("swatch", "zoom-2", "favorite").stdout))
    assert (lint.errors, lint.warnings) == ([], [])


def test_grid_writes_two_halves_at_frame_scale(make_run):
    run = make_run(sizes=[(1179, 2556)])
    out = json.loads(cli("grid", run, "01").stdout)
    assert [Path(p).name for p in out["grids"]] == ["01-top.png", "01-bot.png"]
    with Image.open(out["grids"][0]) as top:
        assert top.width == 60 + wf.CONTENT_W * wf.GRID_SCALE
        assert top.height == (380 + 54) * wf.GRID_SCALE
