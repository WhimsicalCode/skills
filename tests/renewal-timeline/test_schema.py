"""events.json validation: every problem reported at once, with where it is."""
import ast
import json
import subprocess
import sys

import build_board
import pytest
from conftest import SCRIPT, example


def errors(data):
    return build_board.validate(data).errors


def warnings(data):
    return build_board.validate(data).warnings


def has(problems, path, words=""):
    return any(p.startswith(f"{path}:") and words in p for p in problems)


def test_example_is_valid():
    p = build_board.validate(example())
    assert p.errors == [] and p.warnings == []


def test_minimal_file_is_valid():
    data = {"customer": "Globex", "vendor": "Acme", "expiry_date": "2026-11-30",
            "events": [{"date": "2026-08-11", "side": "vendor", "phase": "Outreach", "title": "Hello"}]}
    assert errors(data) == []


@pytest.mark.parametrize("key", ["customer", "vendor", "expiry_date", "events"])
def test_required_top_level(key):
    data = example()
    del data[key]
    assert has(errors(data), key, "required")


def test_reports_every_problem_at_once():
    data = example()
    data["events"][0]["date"] = "2026/08/11"
    data["events"][1]["side"] = "them"
    data["events"][2]["kind"] = "big"
    del data["events"][3]["title"]
    found = errors(data)
    assert has(found, "events[0].date", "2026/08/11")
    assert has(found, "events[1].side")
    assert has(found, "events[2].kind")
    assert has(found, "events[3].title", "required")


def test_events_must_be_in_date_order():
    data = example()
    data["events"][2]["date"] = "2026-08-01"
    assert has(errors(data), "events[2].date", "date order")


def test_same_day_events_keep_their_order():
    data = example()
    data["events"][1]["date"] = data["events"][0]["date"]
    assert errors(data) == []


def test_phase_cannot_come_back():
    data = example()
    data["events"][2]["phase"] = "Finding the owner"
    data["events"][1]["phase"] = "Context & chasing a decision"
    assert has(errors(data), "events[2].phase", "already ended")


def test_phase_prefix_counts_as_same_phase():
    data = example()
    data["events"][1]["phase"] = "Phase 1 · Finding the owner"
    assert errors(data) == []


@pytest.mark.parametrize("amount", [None, "$41,040", -5, True])
def test_offer_amount_must_be_a_number(amount):
    data = example()
    data["events"][3]["offer"]["amount"] = amount
    assert has(errors(data), "events[3].offer.amount")


def test_offer_interval_values():
    data = example()
    data["events"][3]["offer"]["interval"] = "annual"
    assert has(errors(data), "events[3].offer.interval", "year")


def test_interval_count_needs_interval():
    data = example()
    del data["events"][3]["offer"]["interval"]
    data["events"][3]["offer"]["interval_count"] = 3
    assert has(errors(data), "events[3].offer.interval_count")


def test_offer_list_paths_are_indexed():
    data = example()
    data["events"][4]["offer"] = [{"amount": 1, "interval": "year"}, {"amount": "lots"}]
    assert has(errors(data), "events[4].offer[1].amount")


def test_quantity_times_price_mismatch_is_a_warning():
    data = example()
    data["events"][3]["offer"]["amount"] = 40000
    assert errors(data) == []
    assert has(warnings(data), "events[3].offer", "41,040")


def test_text_quantity_and_price_are_allowed():
    data = example()
    data["events"][3]["offer"] = {"quantity": "Unlimited", "unit_price": "$456 / $400 tiers",
                                  "amount": 41040, "interval": "year"}
    assert errors(data) == [] and warnings(data) == []


def test_only_one_acceptance():
    data = example()
    data["events"][6]["kind"] = "acceptance"
    assert has(errors(data), "events[6].kind", "only one")


def test_acceptance_after_several_options_needs_its_offer():
    data = example()
    data["events"][4]["offer"] = [{"amount": 1, "interval": "year"}, {"amount": 2, "interval": "year"}]
    del data["events"][5]["offer"]
    assert has(errors(data), "events[5]", "several options")


def test_contract_new_must_match_accepted_offer():
    data = example()
    data["contract"]["new"] = {"quantity": 100, "unit_price": 504, "amount": 55000, "interval": "year"}
    assert has(errors(data), "contract.new.amount", "50,400")


def test_contract_new_is_derived_when_missing():
    deal = build_board.deal(example())
    assert deal["new"]["amount"] == 50400


def test_usage_counts_are_whole_numbers():
    data = example()
    data["usage"]["active_90d"] = "96"
    assert has(errors(data), "usage.active_90d")


def test_usage_active_above_current_is_a_warning():
    data = example()
    data["usage"]["active_30d"] = 200
    assert errors(data) == []
    assert has(warnings(data), "usage.active_30d")


def test_usage_extra_fields_are_kept():
    data = example()
    data["usage"]["removals_by_date"] = {"2026-10-21": 12}
    assert errors(data) == []


def test_unknown_fields_are_ignored():
    data = example()
    data["crm_deal_id"] = "123"
    data["events"][0]["sentiment"] = "positive"
    assert errors(data) == []


def test_long_title_and_detail_are_warnings():
    data = example()
    data["events"][0]["title"] = "x" * 60
    data["events"][0]["detail"] = ["y" * 70, "z" * 70, "w" * 10]
    assert errors(data) == []
    found = warnings(data)
    assert has(found, "events[0].title") and has(found, "events[0].detail")


def test_cli_prints_all_errors_and_exits(tmp_path):
    data = example()
    data["events"][0]["date"] = "soon"
    data["vendor"] = ""
    f = tmp_path / "events.json"
    f.write_text(json.dumps(data))
    out = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
    assert out.returncode != 0
    assert "has 2 problems" in out.stderr
    assert "events[0].date" in out.stderr and "vendor" in out.stderr


def test_cli_explains_bad_json(tmp_path):
    f = tmp_path / "events.json"
    f.write_text('{"customer": "Globex",}')
    out = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
    assert out.returncode != 0 and "not valid JSON (line 1" in out.stderr


def test_script_runs_on_python_3_9():
    # Users run it with whatever python3 they have; macOS ships 3.9. CI runs a newer Python, so
    # check the syntax against 3.9 here. (tests/repo checks it imports only the standard library.)
    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))


def test_title_must_be_text():
    data = example()
    data["title"] = ""
    assert has(errors(data), "title")


def test_only_blockers_resolve():
    data = example()
    data["events"][0]["resolved"] = "2026-11-08"
    assert has(errors(data), "events[0].resolved", "only a blocker")


def test_resolved_not_before_the_blocker():
    data = example()
    data["events"][7]["resolved"] = "2026-11-01"
    assert has(errors(data), "events[7].resolved", "before the blocker")


def test_very_long_title_is_a_warning():
    data = example()
    data["title"] = "x" * 80
    assert errors(data) == [] and has(warnings(data), "title", "70")


def test_loose_price_fields_are_a_warning():
    data = example()
    data["events"][3]["annual"] = 41040
    data["events"][3]["rate"] = 456
    assert errors(data) == []
    assert has(warnings(data), "events[3]", "annual, rate look like a price")


def test_numbered_phase_is_a_warning():
    data = example()
    data["events"][0]["phase"] = "Phase 1 · Finding the owner"
    assert has(warnings(data), "events[0].phase", "prefix")


def test_pricing_table_field_is_a_warning():
    data = example()
    data["pricing_table"] = []
    assert has(warnings(data), "pricing_table", "built from")
