import json
import subprocess
import sys

from conftest import BOARD, EXAMPLE, SCRIPT, SKILL, example, run_script, write

TABLE_ID = "<id of the table the first call adds>"


def run(*args, board_id="B", check=True):
    extra = [] if "--check" in map(str, args) or board_id is None else ["--board-id", board_id]
    return run_script(*args, *extra, check=check)


def call(*args, **kw):
    return json.loads(run(*args, **kw).stdout)


def operations(*args):
    return call(*args)["arguments"]["operations"]


def cards(ops):
    return [o for o in ops if o.get("shape_type") == "rect" and o.get("width") == 420]


def banners(ops):
    return [o for o in ops if o.get("height") == 50 and o.get("width") == 1040]


def table(ops):
    """The pricing table op, read back as headers, cell texts and the index of the final row."""
    op = [o for o in ops if o.get("type") == "table"][0]
    rows = [[c["text"] if isinstance(c, dict) else c for c in row] for row in op["rows"]]
    final = [i for i, row in enumerate(op["rows"]) if isinstance(row[0], dict)]
    return {"columns": [c["header"] for c in op["columns"]], "rows": rows,
            "final_row": final[0] if final else None, "op": op}


# ---------------------------------------------------------------- new board

def test_output_is_the_edit_call():
    result = call(EXAMPLE, board_id="https://whimsical.com/globex-renewal-timeline-A21LFsmo5f3T3DuAV3aKCr?ref=mcp")
    assert result["tool"] == "edit"
    assert result["arguments"]["id"] == "A21LFsmo5f3T3DuAV3aKCr"
    move = result["then"]["arguments"]["operations"]
    assert move == [{"op": "update", "id": TABLE_ID, "x": 0, "y": -320}]


def test_board_id_is_required():
    out = subprocess.run([sys.executable, str(SCRIPT), str(EXAMPLE)], capture_output=True, text=True)
    assert out.returncode != 0 and "--board-id" in out.stderr


def test_new_board_layout_rules():
    ops = operations(EXAMPLE)
    cs = cards(ops)
    events = example()["events"]
    assert len(cs) == len(events)
    for card, ev in zip(cs, events):
        assert card["x"] == (0 if ev["side"] == "vendor" else 620)
    pills = [o for o in ops if o.get("shape_type") == "pill" and o["width"] == 120]
    for card, pill in zip(cs, pills):
        assert pill["y"] == card["y"] + 40
    expiry = [o for o in ops if o.get("shape_type") == "pill" and o["width"] == 240][0]
    assert expiry["y"] == cs[-1]["y"] + 160
    line = [o for o in ops if o.get("width") == 6][0]
    assert line["height"] == expiry["y"] + 40
    bs = banners(ops)
    assert bs[0]["y"] == 0
    assert bs[-1]["color"] == "green"
    assert all(b["color"] == "dark-purple" for b in bs[:-1])


def test_only_whimsical_color_keys():
    keys = {"blue", "orange", "green", "yellow", "silver", "red", "dark-purple", "default"}
    colors = {o["color"] for o in operations(EXAMPLE) if "color" in o}
    assert colors <= keys


def test_only_a_final_close_phase_is_green(tmp_path):
    data = example()
    data["events"] = data["events"][:6]  # ends in Negotiation
    assert all(b["color"] == "dark-purple" for b in banners(operations(write(tmp_path, data))))
    data = example()
    data["events"][0]["phase"] = data["events"][1]["phase"] = "Enclosed redlines"  # "close" inside a word
    bs = banners(operations(write(tmp_path, data)))
    assert bs[0]["color"] == "dark-purple" and bs[-1]["color"] == "green"


def test_header_is_stacked_title_subtitle_table_legends():
    ops = operations(EXAMPLE)
    title, subtitle = ops[0], ops[1]
    table_y = call(EXAMPLE)["then"]["arguments"]["operations"][0]["y"]
    legend = [o for o in ops if o.get("width") == 200][0]
    assert title["y"] < subtitle["y"] < table_y < legend["y"] < 0
    assert table_y + 40 * 5 + 40 == legend["y"]  # 4 rows + header, then a 40 px gap
    assert "height" not in title and title["color"] == "default"


def test_kinds_add_markers():
    texts = [o["text"] for o in cards(operations(EXAMPLE))]
    assert any("✅" in t for t in texts)
    assert any(t.startswith("**⚠️") for t in texts)


def test_kind_defaults_to_side():
    for card, ev in zip(cards(operations(EXAMPLE)), example()["events"]):
        if "kind" not in ev:
            expected = ("blue", "outline") if ev["side"] == "vendor" else ("orange", "outline")
            assert (card["color"], card["deco"]) == expected


def test_offer_amount_added_to_card_title():
    texts = [o["text"] for o in cards(operations(EXAMPLE))]
    assert "**Asks for 90 seats at $456 = $41,040**" in texts[3]


def test_amount_not_repeated_when_title_has_it(tmp_path):
    data = example()
    data["events"][3]["title"] = "Asks for $41,040"
    texts = [o["text"] for o in cards(operations(write(tmp_path, data)))]
    assert texts[3].startswith("**Asks for $41,040**")


def test_detail_list_becomes_lines():
    texts = [o["text"] for o in cards(operations(EXAMPLE))]
    assert texts[2] == "**Usage recap sent**\n104 seats in use, 96 active in 90 days\nRenewal date Nov 30"


def test_phase_prefix_is_not_doubled(tmp_path):
    data = example()
    for ev in data["events"]:
        ev["phase"] = "Phase 9 · " + ev["phase"]
    assert banners(operations(write(tmp_path, data)))[0]["text"] == "Phase 1 · Finding the owner"


def test_year_defaults_to_expiry_year():
    assert operations(EXAMPLE)[0]["text"] == "Globex 2026 Renewal Timeline"


# ---------------------------------------------------------------- pricing table

def test_pricing_table_comes_from_offers():
    t = table(operations(EXAMPLE))
    assert t["columns"] == ["Date", "From", "Seats", "Price", "Annual"]
    assert t["rows"] == [
        ["Current", "Contract", "120", "$480", "$57,600"],
        ["Sep 22", "Globex", "90", "$456", "$41,040"],
        ["Oct 2", "Acme", "110", "$504", "$55,440"],
        ["Oct 20 ✅", "Final", "100", "$504", "$50,400"],
    ]
    assert t["final_row"] == 3


def test_table_has_no_position_or_styles_map():
    op = table(operations(EXAMPLE))["op"]
    # The MCP ignores x/y on a new table (hence the `then` move) and refuses `styles`.
    assert "x" not in op and "y" not in op and "styles" not in op
    assert sum(c["width"] for c in op["columns"]) + 10 == 1040
    assert op["rows"][-1][0] == {"text": "Oct 20 ✅", "color": "green", "bold": True}


def test_table_cells_escape_markdown(tmp_path):
    data = example()
    data["events"][3]["offer"]["unit_price"] = "$456 | *intro* rate"
    assert table(operations(write(tmp_path, data)))["rows"][1][3] == "$456 \\| \\*intro\\* rate"


def test_acceptance_without_offer_finalizes_the_last_offer(tmp_path):
    data = example()
    del data["events"][5]["offer"]
    t = table(operations(write(tmp_path, data)))
    assert t["rows"][-1] == ["Oct 20 ✅", "Final", "110", "$504", "$55,440"]
    assert len(t["rows"]) == 3


def test_one_offer_per_option(tmp_path):
    data = example()
    data["events"][4]["offer"] = [
        {"quantity": "Unlimited", "amount": 60000, "interval": "year"},
        {"quantity": 110, "unit_price": "$504 / $480 tiers", "amount": 54000, "interval": "year"},
    ]
    rows = table(operations(write(tmp_path, data)))["rows"]
    assert rows[2] == ["Oct 2", "Acme", "Unlimited", "", "$60,000"]
    assert rows[3] == ["Oct 2", "Acme", "110", "$504 / $480 tiers", "$54,000"]


def test_mixed_intervals_label_each_amount(tmp_path):
    data = example()
    data["events"][3]["offer"] = {"amount": 3420, "interval": "month"}
    data["events"][4]["offer"] = {"amount": 20000, "note": "setup fee"}
    t = table(operations(write(tmp_path, data)))
    assert t["columns"][-1] == "Amount"
    assert t["rows"][1][-1] == "$3,420/mo"
    assert t["rows"][2][-1] == "$20,000 one-time"
    assert t["rows"][0][-1] == "$57,600/yr"


def test_monthly_deal_header(tmp_path):
    data = example()
    data["contract"]["previous"] = {"amount": 4800, "interval": "month"}
    for ev in data["events"]:
        if "offer" in ev:
            ev["offer"] = {"amount": ev["offer"]["amount"] / 12, "interval": "month"}
    t = table(operations(write(tmp_path, data)))
    assert t["columns"][-1] == "Monthly"
    assert t["rows"][-1][-1] == "$4,200"


def test_currency_symbol(tmp_path):
    data = example()
    data["currency"] = "eur"
    assert table(operations(write(tmp_path, data)))["rows"][0][-1] == "€57,600"
    data["currency"] = "sek"
    assert table(operations(write(tmp_path, data)))["rows"][0][-1] == "SEK 57,600"


def test_no_table_without_prices(tmp_path):
    data = example()
    del data["contract"]
    for ev in data["events"]:
        ev.pop("offer", None)
    result = call(write(tmp_path, data))
    assert "then" not in result
    assert not [o for o in result["arguments"]["operations"] if o.get("type") == "table"]


# ---------------------------------------------------------------- deal numbers and subtitle

def test_deal_numbers():
    deal = call(EXAMPLE, "--check")["deal"]
    assert (deal["previous_annual"], deal["new_annual"]) == (57600, 50400)
    assert (deal["change"], deal["change_pct"], deal["nrr_pct"]) == (-7200, -12.5, 87.5)


def test_deal_annualizes_monthly_terms(tmp_path):
    data = example()
    data["contract"] = {"previous": {"amount": 4800, "interval": "month"},
                        "new": {"amount": 50400, "interval": "year"}}
    data["events"][5]["offer"] = {"amount": 50400, "interval": "year"}
    deal = call(write(tmp_path, data), "--check")["deal"]
    assert deal["previous_annual"] == 57600 and deal["nrr_pct"] == 87.5


def test_no_nrr_for_one_time_fees(tmp_path):
    data = example()
    data["contract"]["previous"] = {"amount": 400000, "note": "6-month project"}
    data["events"][5]["offer"] = {"amount": 350000, "note": "Phase 2 SOW"}
    deal = call(write(tmp_path, data), "--check")["deal"]
    assert deal["nrr_pct"] is None and deal["change"] is None


def test_subtitle_is_computed():
    assert operations(EXAMPLE)[1]["text"] == (
        "Aug 11 to Nov 4, 2026 · 120 seats at $480 for $57,600/yr → "
        "100 seats at $504 for $50,400/yr (-12.5%) · Contract expiry Nov 30")


def test_subtitle_before_agreement(tmp_path):
    data = example()
    data["events"] = data["events"][:5]
    subtitle = operations(write(tmp_path, data))[1]["text"]
    assert "Currently 120 seats at $480 for $57,600/yr" in subtitle
    assert "→" not in subtitle


# ---------------------------------------------------------------- appending to a board

PO = {"date": "2026-11-09", "side": "customer", "phase": "Close", "title": "PO 4471 issued", "detail": "For $50,400"}
SIGNED = {"date": "2026-11-12", "side": "vendor", "kind": "milestone", "phase": "Signed", "title": "Order form signed"}


def with_new_events(tmp_path, *events):
    data = example()
    data["events"].extend(events)
    return write(tmp_path, data)


def test_append_reads_the_board(tmp_path):
    ops = operations(with_new_events(tmp_path, PO), "--append", BOARD)
    assert [c["text"] for c in cards(ops)] == ["**PO 4471 issued**\nFor $50,400"]
    assert (cards(ops)[0]["x"], cards(ops)[0]["y"]) == (620, 1440)
    updates = {o["id"]: o for o in ops if o["op"] == "update"}
    expiry = [o for o in ops if o.get("width") == 240][0]
    assert expiry["y"] == 1600 and expiry["text"] == "Nov 30 · Contract expiry"  # re-added below the new card
    assert {"op": "delete", "id": "9bHUbYff1Y52TxGP8JngQJ"} in ops
    assert ops.index(expiry) > ops.index(cards(ops)[0])                      # drawn above the line
    assert updates["L5N6V61SCpdaySWtWZjw4r"]["height"] == 1640  # center line
    assert updates["FFCfk2TPYJD8BisQKSsrG4"]["text"].startswith("Aug 11 to Nov 9, 2026")  # subtitle
    assert not banners(ops)  # same phase


def test_append_new_phase_continues_numbering_and_recolors(tmp_path):
    ops = operations(with_new_events(tmp_path, PO, SIGNED), "--append", BOARD)
    banner = banners(ops)[0]
    assert banner["text"] == "Phase 5 · Signed" and banner["color"] == "green"
    assert banner["y"] == 1440 + 140
    assert {"op": "update", "id": "TcZu1SHCsyJpU7UNesYN4j", "color": "dark-purple"} in ops


def test_append_keeps_the_table_unless_prices_changed(tmp_path):
    result = call(with_new_events(tmp_path, PO), "--append", BOARD)
    assert "then" not in result
    ops = result["arguments"]["operations"]
    assert not [o for o in ops if o.get("type") == "table"]
    assert [o["id"] for o in ops if o["op"] == "delete"] == ["9bHUbYff1Y52TxGP8JngQJ"]  # only the old marker


def test_append_redraws_the_table_when_prices_change(tmp_path):
    amended = {"date": "2026-11-09", "side": "vendor", "phase": "Close", "title": "Amended: 105 seats",
               "offer": {"quantity": 105, "unit_price": 504, "amount": 52920, "interval": "year"}}
    result = call(with_new_events(tmp_path, amended), "--append", BOARD)
    ops = result["arguments"]["operations"]
    assert {"op": "delete", "id": "Stzyk9B4HkRJ5HsShPMvXx"} in ops
    assert len(table(ops)["rows"]) == 4  # offers after the acceptance aren't shown
    assert result["then"]["arguments"]["operations"][0] == {"op": "update", "id": TABLE_ID, "x": 0, "y": -320}


def test_append_grows_the_table_upwards(tmp_path):
    data = example()
    data["events"][4]["offer"] = [data["events"][4]["offer"], {"quantity": 120, "amount": 58000, "interval": "year"}]
    data["events"].append({**PO, "offer": {"amount": 50400, "interval": "year"}})
    result = call(write(tmp_path, data), "--append", BOARD)
    ops = result["arguments"]["operations"]
    assert result["then"]["arguments"]["operations"][0]["y"] == -360  # one more row, same bottom
    moved = {o["id"]: o for o in ops if o["op"] == "update" and "y" in o}
    assert moved["FFCfk2TPYJD8BisQKSsrG4"]["y"] == -420 and moved["DL9L3rLnn1zSTY2i2koKgR"]["y"] == -500


def test_append_with_nothing_new_still_tidies():
    ops = operations(EXAMPLE, "--append", BOARD)
    assert not cards(ops)
    assert {o["op"] for o in ops} == {"update"}


def test_append_warns_when_the_board_differs(tmp_path):
    data = example()
    data["events"][2]["title"] = "Something else"
    out = run(write(tmp_path, data), "--append", BOARD)
    assert "board card 3" in out.stderr


def test_append_matches_cards_whose_line_breaks_fetch_flattened(tmp_path):
    out = run(with_new_events(tmp_path, PO), "--append", BOARD)
    assert "warning" not in out.stderr


def test_append_refuses_a_file_with_fewer_events(tmp_path):
    data = example()
    data["events"] = data["events"][:5]
    out = run(write(tmp_path, data), "--append", BOARD, check=False)
    assert out.returncode != 0 and "Keep every event" in out.stderr


def test_append_refuses_a_truncated_listing(tmp_path):
    raw = json.loads(BOARD.read_text())
    raw["cursor"] = "abc123"
    out = run(EXAMPLE, "--append", write(tmp_path, raw, "board.json"), check=False)
    assert out.returncode != 0 and "more pages" in out.stderr


def test_append_reads_several_pages(tmp_path):
    raw = json.loads(BOARD.read_text())
    header, *rows = raw["text"].split("type,id,parentId,x,y,width,height,color,locked,text\n")[1].split("\n")
    rows = [r for r in [header, *rows] if r.startswith(("shape", "text", "table"))]
    columns = "type,id,parentId,x,y,width,height,color,locked,text\n"
    page1 = write(tmp_path, {"text": columns + "\n".join(rows[:10])}, "p1.json")
    page2 = write(tmp_path, {"text": columns + "\n".join(rows[10:])}, "p2.json")
    ops = operations(with_new_events(tmp_path, PO), "--append", page1, page2)
    assert (cards(ops)[0]["x"], cards(ops)[0]["y"]) == (620, 1440)


def test_append_refuses_another_kind_of_board(tmp_path):
    other = {"text": "Board: 1 objects.\n\ntype,id,parentId,x,y,width,height,color,locked,text\n"
                     "shape:rect,A,,0,0,100,100,Blue,false,Hello\n"}
    out = run(EXAMPLE, "--append", write(tmp_path, other, "board.json"), check=False)
    assert out.returncode != 0 and "doesn't look like a renewal timeline" in out.stderr


# ---------------------------------------------------------------- from the second benchmark run

def test_custom_title(tmp_path):
    data = example()
    data["title"] = "Globex 2026 Renewal Timeline (skill test 2)"
    assert operations(write(tmp_path, data))[0]["text"] == "Globex 2026 Renewal Timeline (skill test 2)"


def test_append_finds_and_updates_a_custom_title(tmp_path):
    data = example()
    data["title"] = "Globex renewal"
    ops = operations(write(tmp_path, data), "--append", BOARD)
    assert {"op": "update", "id": "DL9L3rLnn1zSTY2i2koKgR", "text": "Globex renewal"} in ops


def test_customer_milestone_is_filled_orange(tmp_path):
    data = example()
    data["events"][1]["kind"] = "milestone"
    card = cards(operations(write(tmp_path, data)))[1]
    assert (card["color"], card["deco"]) == ("orange", "fill")
    assert (cards(operations(EXAMPLE))[4]["color"], cards(operations(EXAMPLE))[4]["deco"]) == ("blue", "fill")


def test_skill_finds_the_table_id_even_when_the_reply_hides_it():
    # Claude Code shows the edit reply without the table's id; claude.ai shows it.
    text = (SKILL / "SKILL.md").read_text()
    assert "otherwise find it with `fetch`, `select_kinds: [\"table\"]`" in text


# ---------------------------------------------------------------- from the update run

LATE = {"date": "2026-12-02", "side": "vendor", "kind": "milestone", "phase": "Close", "title": "Countersigned"}


def small_reads(tmp_path):
    """What read_calls asks for, cut from the full fixture: grep for the marker and banners, and the texts and table."""
    raw = json.loads(BOARD.read_text())["text"]
    head, body = raw.split("type,id,parentId,x,y,width,height,color,locked,text\n")
    rows = [r for r in body.split("\n\n")[0].split("\n") if r]
    grep = [r for r in rows if "Contract expiry" in r or ",Phase " in r]
    kinds = [r for r in rows if r.startswith(("text,", "table,"))]
    columns = "type,id,parentId,x,y,width,height,color,locked,text\n"
    return (write(tmp_path, {"text": columns + "\n".join(grep)}, "board.json"),
            write(tmp_path, {"text": columns + "\n".join(kinds)}, "board-2.json"))


def drawn(data, count=None):
    data["board"] = {"id": "A21LFsmo5f3T3DuAV3aKCr", "events": len(data["events"]) if count is None else count}
    return data


def test_expiry_marker_sits_at_its_date(tmp_path):
    data = example()
    data["events"].append(LATE)
    ops = operations(write(tmp_path, data))
    expiry = [o for o in ops if o.get("width") == 240][0]
    po, late = cards(ops)[-2], cards(ops)[-1]
    assert expiry["y"] == po["y"] + 160      # right after the last event before Nov 30
    assert late["y"] == po["y"] + 280        # the marker takes one row
    line = [o for o in ops if o.get("width") == 6][0]
    assert line["height"] == late["y"] + 120 + 40


def test_new_phase_after_the_marker_clears_it(tmp_path):
    data = example()
    data["events"].append({**LATE, "phase": "Signed"})
    ops = operations(write(tmp_path, data))
    expiry = [o for o in ops if o.get("width") == 240][0]
    assert banners(ops)[-1]["y"] >= expiry["y"] + 50


def test_read_calls_are_small_once_recorded(tmp_path):
    data = drawn(example())
    data["events"][7]["resolved"] = "2026-11-08"
    calls = call(write(tmp_path, data), "--read", board_id=None)
    assert [c["tool"] for c in calls] == ["fetch", "fetch"]
    assert calls[0]["arguments"]["grep_text"] == ["Contract expiry", "Phase ", "PO pending"]
    assert calls[1]["arguments"]["select_kinds"] == ["text", "table"]
    assert calls[0]["arguments"]["id"] == "A21LFsmo5f3T3DuAV3aKCr"  # taken from events.json


def test_read_calls_fall_back_to_the_whole_board():
    calls = call(EXAMPLE, "--read")
    assert len(calls) == 1 and calls[0]["arguments"]["limit"] == 200


def test_done_records_the_board(tmp_path):
    f = write(tmp_path, example())
    out = run(f, "--done", board_id="https://whimsical.com/x-A21LFsmo5f3T3DuAV3aKCr")
    assert "board A21LFsmo5f3T3DuAV3aKCr" in out.stdout
    assert json.loads(f.read_text())["board"] == {
        "id": "A21LFsmo5f3T3DuAV3aKCr", "url": "https://whimsical.com/A21LFsmo5f3T3DuAV3aKCr", "events": 8}


def test_append_from_the_small_reads(tmp_path):
    data = drawn(example(), 8)
    data["events"].append(PO)
    ops = operations(write(tmp_path, data), "--append", *small_reads(tmp_path))
    assert [c["text"] for c in cards(ops)] == ["**PO 4471 issued**\nFor $50,400"]
    segment = [o for o in ops if o.get("width") == 6][0]
    assert (segment["op"], segment["y"], segment["y"] + segment["height"]) == ("add", 1500, 1640)
    assert ops.index(segment) < ops.index(cards(ops)[0])  # beneath the new card


def test_small_reads_need_the_recorded_count(tmp_path):
    data = example()
    data["events"].append(PO)
    out = run(write(tmp_path, data), "--append", *small_reads(tmp_path), check=False)
    assert out.returncode != 0 and "board.events" in out.stderr


def test_append_after_expiry_keeps_the_marker(tmp_path):
    data = drawn(example(), 8)
    data["events"].append(LATE)
    ops = operations(write(tmp_path, data), "--append", *small_reads(tmp_path))
    assert not [o for o in ops if o.get("width") == 240 or o["op"] == "delete"]
    assert cards(ops)[0]["y"] == 1300 + 280
    segment = [o for o in ops if o.get("width") == 6][0]
    assert segment["y"] == 1460 + 50  # starts under the marker, which stays on top


def test_resolved_blocker_card(tmp_path):
    data = example()
    data["events"][7]["resolved"] = "2026-11-08"
    card = cards(operations(write(tmp_path, data)))[7]
    assert card["text"].startswith("**PO pending · resolved Nov 8**")
    assert (card["color"], card["deco"]) == ("yellow", "outline")


def test_append_resolves_a_blocker_on_the_board(tmp_path):
    data = drawn(example(), 8)
    data["events"][7]["resolved"] = "2026-11-09"
    data["events"].append(PO)
    ops = operations(write(tmp_path, data), "--append", BOARD)
    update = [o for o in ops if o.get("id") == "5dwVorsKyBn9fZ2xPix2d6"][0]
    assert update == {"op": "update", "id": "5dwVorsKyBn9fZ2xPix2d6",
                      "text": "**PO pending · resolved Nov 9**\nWaiting on finance approval",
                      "color": "yellow", "deco": "outline"}


def test_append_warns_when_the_layout_differs(tmp_path):
    data = drawn(example(), 7)  # claims one event fewer than the board shows
    data["events"].append(PO)
    out = run(write(tmp_path, data), "--append", *small_reads(tmp_path))
    assert "aren't where the first 7 events put them" in out.stderr


# ---------------------------------------------------------------- from benchmark run 3

def test_long_title_shrinks_to_stay_on_one_line(tmp_path):
    data = example()
    data["title"] = "Globex 2026 Renewal Timeline (second review)"  # 44 characters: wrapped at l3
    ops = operations(write(tmp_path, data))
    title, subtitle = ops[0], ops[1]
    assert title["font_size"] == "l2"
    assert title["y"] + 48 + 8 == subtitle["y"]


def test_default_title_stays_large():
    title, subtitle = operations(EXAMPLE)[:2]
    assert title["font_size"] == "l3" and title["y"] + 72 + 8 == subtitle["y"]


def test_append_puts_a_moved_title_back(tmp_path):
    raw = json.loads(BOARD.read_text())
    raw["text"] = raw["text"].replace("text,DL9L3rLnn1zSTY2i2koKgR,,0,-460,", "text,DL9L3rLnn1zSTY2i2koKgR,,0,-532,")
    data = example()
    data["title"] = "Globex 2026 Renewal Timeline (second look)"
    ops = operations(write(tmp_path, data), "--append", write(tmp_path, raw, "board.json"))
    update = [o for o in ops if o.get("id") == "DL9L3rLnn1zSTY2i2koKgR"][0]
    assert update == {"op": "update", "id": "DL9L3rLnn1zSTY2i2koKgR", "y": -380 - 8 - 48,
                      "text": "Globex 2026 Renewal Timeline (second look)", "font_size": "l2"}


# ---------------------------------------------------------------- the full example (README screenshot)

FULL = SKILL / "examples" / "full-deal.example.json"


def test_full_example_is_clean_and_complete():
    out = run(FULL)
    assert out.stderr == ""
    ops = json.loads(out.stdout)["arguments"]["operations"]
    assert len(cards(ops)) == 22 and len(banners(ops)) == 4
    t = table(ops)
    assert len(t["rows"]) == 8 and t["rows"][-1] == ["Nov 20 ✅", "Final", "320", "$168", "$53,760"]
    deal = call(FULL, "--check")["deal"]
    assert (deal["change"], deal["nrr_pct"]) == (8760, 119.5)
    # Everything happens before the Dec 31 expiry, so the marker closes the timeline.
    expiry = [o for o in ops if o.get("width") == 240][0]
    assert expiry["y"] == cards(ops)[-1]["y"] + 160
    resolved = [c for c in cards(ops) if "resolved Oct 20" in c["text"]][0]
    assert (resolved["color"], resolved["deco"]) == ("yellow", "outline")


def test_output_cut_short_is_not_an_error():
    out = subprocess.run(f'"{sys.executable}" "{SCRIPT}" "{EXAMPLE}" --board-id B | head -c 10',
                         shell=True, capture_output=True, text=True)
    assert "Traceback" not in out.stderr
