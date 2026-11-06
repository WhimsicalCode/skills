#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Check events.json and turn it into the Whimsical MCP `edit` call that draws the board.

  python3 build_board.py events.json --check
      Check the file; print the deal numbers (old and new terms, change, NRR).
  python3 build_board.py events.json --board-id <id>
      New board: print {"tool": "edit", "arguments": {...}} to pass to the edit tool as is.
  python3 build_board.py events.json --board-id <id> --read
      Existing board: print the fetch calls to make. Save each reply (its rows are enough).
  python3 build_board.py events.json --board-id <id> --append board-1.txt [board-2.txt ...]
      Adds the events not on the board yet, moves the expiry marker, marks resolved blockers,
      and redraws the subtitle and pricing table from the whole file.
  python3 build_board.py events.json --board-id <id> --done
      Once the board looks right: record it and how many events it shows in events.json.

The script never calls Whimsical; it only reads files and prints the next call.
Schema: references/event-schema.md. Layout spec: references/board-layout.md
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date

# Layout constants (see references/board-layout.md)
WIDTH = 1040
CARD_W, CARD_H = 420, 120
VENDOR_X, CUSTOMER_X = 0, 620
PILL_X, PILL_W, PILL_H, PILL_DY = 460, 120, 40, 40
STEP = 140
BANNER_H = 50
BANNER_TO_CARD = 80
EXPIRY_X, EXPIRY_W, EXPIRY_H = 400, 240, 50
EXPIRY_GAP = 160          # last card y -> expiry y (the marker takes one row of the rhythm)
LINE_X, LINE_W = 517, 6
LINE_TAIL = 40            # center line height = expiry y + this

# Header, stacked upwards from the legends: title, subtitle, pricing table, legends.
LEGEND_Y, LEGEND_W, LEGEND_H = -80, 200, 40
TABLE_ROW_H = 40          # Whimsical draws table rows 40 px tall, header included
TABLE_GAP = 40            # table bottom -> legends
TABLE_WIDTHS = (140, 180, 140, 330, 240)  # + 10 px of border = 1040
SUBTITLE_GAP = 40         # subtitle -> table (or legends)
SUBTITLE_H = 20
TITLE_GAP = 8             # title bottom -> subtitle top
# The title's font shrinks so it stays on one line in 1040 px: (font size, line height, characters).
# Measured on Whimsical: 36 characters fit at l3, 56 at l2, 70 at l1.
TITLE_SIZES = (("l3", 72, 36), ("l2", 48, 56), ("l1", 36, 70))

# What fits on a 420 x 120 card at font size s (warnings only).
TITLE_MAX = 50
DETAIL_LINE_CHARS = 60
DETAIL_MAX_LINES = 3

# Whimsical color keys. `purple` draws pink and `slate` isn't a key, so banners use dark-purple
# and text uses default. `green` is the palette's "Mint".
KIND_STYLE = {
    "routine": ("blue", "outline"),
    "milestone": ("blue", "fill"),
    "customer": ("orange", "outline"),
    "acceptance": ("green", "fill"),
    "blocker": ("yellow", "fill"),
}
CUSTOMER_MILESTONE = ("orange", "fill")  # a key moment on the customer's side: PO issued, contract signed
RESOLVED_BLOCKER = ("yellow", "outline")
PHASE_COLOR, CLOSE_PHASE_COLOR = "dark-purple", "green"
FINAL_ROW_STYLE = {"color": "green", "bold": True}
DEFAULT_KIND = {"vendor": "routine", "customer": "customer"}
CLOSE_WORDS = ("close", "closed", "signed", "won")

PER_YEAR = {"day": 365, "week": 52, "month": 12, "year": 1}
PERIOD_SHORT = {"day": "day", "week": "wk", "month": "mo", "year": "yr"}
AMOUNT_HEADER = {("year", 1): "Annual", ("month", 1): "Monthly", ("week", 1): "Weekly",
                 ("day", 1): "Daily", (None, 1): "Total"}
CURRENCY_SYMBOL = {"usd": "$", "eur": "€", "gbp": "£", "jpy": "¥", "inr": "₹",
                   "cad": "CA$", "aud": "A$", "nzd": "NZ$", "chf": "CHF "}
USAGE_COUNTS = ("current", "active_90d", "active_30d", "active_removed")
# Price fields that belong in an event's `offer`: set loose on an event, they'd be ignored silently.
LOOSE_PRICE_KEYS = ("amount", "annual", "quantity", "unit_price", "rate", "price", "seats", "units", "offers")
PHASE_PREFIX = re.compile(r"^\s*phase\s+\d+\s*[·:.\-]\s*", re.I)


# ---------------------------------------------------------------- validation

class Problems:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(f"{path}: {message}")


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def check_date(p: Problems, path: str, value) -> bool:
    if not isinstance(value, str):
        p.error(path, "must be a date like 2026-11-05")
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        p.error(path, f"not a date like 2026-11-05: {value!r}")
        return False
    return True


def check_offer(p: Problems, path: str, offer) -> None:
    if not isinstance(offer, dict):
        p.error(path, "must be an object with at least `amount`")
        return
    amount = offer.get("amount")
    if not is_number(amount) or amount < 0:
        p.error(f"{path}.amount", "required: the total per interval, as a number (45000, not \"$45,000\")")
    quantity = offer.get("quantity")
    if quantity is not None and not (is_text(quantity) or (is_number(quantity) and quantity > 0)):
        p.error(f"{path}.quantity", "must be a positive number, or text like \"Unlimited\"")
    unit_price = offer.get("unit_price")
    if unit_price is not None and not (is_text(unit_price) or (is_number(unit_price) and unit_price >= 0)):
        p.error(f"{path}.unit_price", "must be a number, or text like \"$180 first 100, then $150\"")
    interval = offer.get("interval")
    if interval is not None and interval not in PER_YEAR:
        p.error(f"{path}.interval", f"must be one of {', '.join(PER_YEAR)} (leave it out for a one-time fee)")
    if "interval_count" in offer:
        count = offer["interval_count"]
        if interval is None:
            p.error(f"{path}.interval_count", "only makes sense with `interval`")
        elif not isinstance(count, int) or isinstance(count, bool) or count < 1:
            p.error(f"{path}.interval_count", "must be a whole number, 1 or more")
    if "note" in offer and not isinstance(offer["note"], str):
        p.error(f"{path}.note", "must be text")
    if is_number(quantity) and is_number(unit_price) and is_number(amount):
        expected = quantity * unit_price
        if abs(expected - amount) > max(1, 0.01 * amount):
            p.warn(path, f"quantity × unit_price is {expected:,g}, but amount is {amount:,g}. "
                         "Fine for discounts or minimums; otherwise fix one of them")


def event_offers(ev: dict) -> list:
    offer = ev.get("offer")
    if offer is None:
        return []
    return offer if isinstance(offer, list) else [offer]


def phase_label(name: str) -> str:
    return PHASE_PREFIX.sub("", name).strip()


def style_of(ev: dict) -> tuple:
    if kind_of(ev) == "milestone" and ev.get("side") == "customer":
        return CUSTOMER_MILESTONE
    if kind_of(ev) == "blocker" and ev.get("resolved"):
        return RESOLVED_BLOCKER
    return KIND_STYLE[kind_of(ev)]


def kind_of(ev: dict) -> str:
    return ev.get("kind") or DEFAULT_KIND.get(ev.get("side"), "routine")


def detail_lines(ev: dict) -> list:
    detail = ev.get("detail")
    if detail is None:
        return []
    if isinstance(detail, str):
        return [line.strip() for line in detail.split("\n") if line.strip()]
    return [line.strip() for line in detail if line.strip()]


def check_event(p: Problems, i: int, ev) -> None:
    path = f"events[{i}]"
    if not isinstance(ev, dict):
        p.error(path, "must be an object")
        return
    for key in ("date", "side", "phase", "title"):
        if key not in ev:
            p.error(f"{path}.{key}", "required")
    if "date" in ev:
        check_date(p, f"{path}.date", ev["date"])
    if "side" in ev and ev["side"] not in ("vendor", "customer"):
        p.error(f"{path}.side", f"must be \"vendor\" or \"customer\", not {ev['side']!r}")
    if "phase" in ev and not (is_text(ev["phase"]) and phase_label(ev["phase"])):
        p.error(f"{path}.phase", "must be a phase name, like \"Negotiation\"")
    if "title" in ev:
        if not is_text(ev["title"]):
            p.error(f"{path}.title", "must be text")
        elif len(ev["title"].strip()) > TITLE_MAX:
            p.warn(f"{path}.title", f"{len(ev['title'].strip())} characters; a card fits about {TITLE_MAX}")
    if "kind" in ev and ev["kind"] not in KIND_STYLE:
        p.error(f"{path}.kind", f"must be one of {', '.join(KIND_STYLE)}")
    if "resolved" in ev:
        if ev.get("kind") != "blocker":
            p.error(f"{path}.resolved", "only a blocker can be resolved")
        elif check_date(p, f"{path}.resolved", ev["resolved"]) and valid_date(ev.get("date")) \
                and ev["resolved"] < ev["date"]:
            p.error(f"{path}.resolved", f"{ev['resolved']} is before the blocker itself ({ev['date']})")
    detail = ev.get("detail")
    if detail is not None:
        if not (isinstance(detail, str) or (isinstance(detail, list) and all(isinstance(d, str) for d in detail))):
            p.error(f"{path}.detail", "must be text, or a list of short lines")
        else:
            lines = sum(max(1, math.ceil(len(line) / DETAIL_LINE_CHARS)) for line in detail_lines(ev))
            if lines > DETAIL_MAX_LINES:
                p.warn(f"{path}.detail", f"about {lines} lines; a card fits {DETAIL_MAX_LINES} under the title")
    loose = [k for k in LOOSE_PRICE_KEYS if k in ev]
    if loose:
        p.warn(path, f"{', '.join(loose)} look like a price; put prices in `offer` "
                     "(see Prices in event-schema.md), or the pricing table won't show them")
    if is_text(ev.get("phase")) and PHASE_PREFIX.match(ev["phase"]):
        p.warn(f"{path}.phase", "leave out the \"Phase N ·\" prefix; the board numbers phases itself")
    offers = event_offers(ev)
    if isinstance(ev.get("offer"), list) and not offers:
        p.error(f"{path}.offer", "an empty list; leave `offer` out instead")
    for j, offer in enumerate(offers):
        check_offer(p, f"{path}.offer" + (f"[{j}]" if isinstance(ev["offer"], list) else ""), offer)


def valid_date(value) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def check_order(p: Problems, events: list) -> None:
    """Dates never go backwards, and each phase is one unbroken run of events."""
    seen_phases: set[str] = set()
    last_date = last_phase = None
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        day = ev.get("date")
        if valid_date(day):  # bad dates are reported by check_event
            if last_date and day < last_date:
                p.error(f"events[{i}].date", f"{day} comes after {last_date}; list events in date order")
            last_date = max(last_date or day, day)
        phase = ev.get("phase")
        if not is_text(phase):
            continue
        phase = phase_label(phase)
        if phase != last_phase:
            if phase in seen_phases:
                p.error(f"events[{i}].phase", f"\"{phase}\" already ended earlier; a phase must be one "
                                              "unbroken run of events, or the board gets two banners for it")
            seen_phases.add(phase)
            last_phase = phase


def check_acceptance(p: Problems, data: dict) -> None:
    events = [ev for ev in data["events"] if isinstance(ev, dict)]
    accepted = [i for i, ev in enumerate(data["events"]) if isinstance(ev, dict) and ev.get("kind") == "acceptance"]
    if len(accepted) > 1:
        p.error(f"events[{accepted[1]}].kind", "only one event can be the acceptance")
        return
    if not accepted:
        return
    i = accepted[0]
    ev = data["events"][i]
    if len(event_offers(ev)) > 1:
        p.error(f"events[{i}].offer", "the acceptance can carry one offer: the accepted one")
        return
    if not event_offers(ev):
        earlier = [e for e in events[:events.index(ev)] if event_offers(e)]
        if earlier and len(event_offers(earlier[-1])) > 1:
            p.error(f"events[{i}]", "the last offer before it has several options; put the accepted one "
                                    "on the acceptance event as `offer`")


def validate(data) -> Problems:
    p = Problems()
    if not isinstance(data, dict):
        p.error("events.json", "must be a JSON object")
        return p
    for key in ("customer", "vendor"):
        if not is_text(data.get(key)):
            p.error(key, "required: the company name")
    if "expiry_date" not in data:
        p.error("expiry_date", "required: the date the current contract ends")
    else:
        check_date(p, "expiry_date", data["expiry_date"])
    if "year" in data and not (isinstance(data["year"], int) and not isinstance(data["year"], bool)):
        p.error("year", "must be a year like 2026")
    currency = data.get("currency", "usd")
    if not (isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency)):
        p.error("currency", "must be a three-letter code like \"usd\" or \"eur\"")
    if "title" in data and not is_text(data["title"]):
        p.error("title", "must be text, like \"Globex 2026 Renewal Timeline\"")
    elif is_text(data.get("title")) and len(data["title"]) > TITLE_SIZES[-1][2]:
        p.warn("title", f"{len(data['title'])} characters; it fits on one line up to {TITLE_SIZES[-1][2]}")
    if "unit_label" in data and not is_text(data["unit_label"]):
        p.error("unit_label", "must be a word like \"seat\" or \"Editor\"")
    if "as_of" in data:
        check_date(p, "as_of", data["as_of"])

    contract = data.get("contract")
    if contract is not None:
        if not isinstance(contract, dict):
            p.error("contract", "must be an object with `previous` and/or `new`")
        else:
            for key in ("previous", "new"):
                if key in contract:
                    check_offer(p, f"contract.{key}", contract[key])
            if isinstance(contract.get("new"), dict) and "agreed" in contract["new"]:
                check_date(p, "contract.new.agreed", contract["new"]["agreed"])

    usage = data.get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            p.error("usage", "must be an object")
        else:
            for key in USAGE_COUNTS:
                if key in usage and not (isinstance(usage[key], int) and not isinstance(usage[key], bool)
                                         and usage[key] >= 0):
                    p.error(f"usage.{key}", "must be a whole number")
            if "as_of" in usage:
                check_date(p, "usage.as_of", usage["as_of"])
            current = usage.get("current")
            for key in ("active_90d", "active_30d"):
                if is_number(current) and is_number(usage.get(key)) and usage[key] > current:
                    p.warn(f"usage.{key}", f"{usage[key]} is more than current ({current}); "
                                           "active counts are among current members")

    for key in ("open_items",):
        if key in data and not (isinstance(data[key], list) and all(is_text(x) for x in data[key])):
            p.error(key, "must be a list of short sentences")
    if "people" in data:
        people = data["people"]
        if not isinstance(people, list):
            p.error("people", "must be a list")
        else:
            for i, person in enumerate(people):
                if not (isinstance(person, dict) and is_text(person.get("name"))):
                    p.error(f"people[{i}]", "must be an object with at least `name`")

    for key in ("pricing_table", "pricing_rows"):
        if key in data:
            p.warn(key, "is ignored: the pricing table is built from the events' `offer`s")
    events = data.get("events")
    if not isinstance(events, list) or not events:
        p.error("events", "required: a list of events, oldest first")
        return p
    for i, ev in enumerate(events):
        check_event(p, i, ev)
    check_order(p, events)
    check_acceptance(p, data)

    if not p.errors:
        new = (data.get("contract") or {}).get("new")
        final = final_offer(data)
        if isinstance(new, dict) and final and is_number(new.get("amount")) and new["amount"] != final["amount"]:
            p.error("contract.new.amount", f"{new['amount']:,g}, but the accepted offer's amount is "
                                           f"{final['amount']:,g}")
    return p


# ---------------------------------------------------------------- formatting

def fmt_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def money(value, currency: str) -> str:
    code = currency.lower()
    symbol = CURRENCY_SYMBOL.get(code, code.upper() + " ")
    sign = "-" if value < 0 else ""
    value = abs(value)
    number = f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}"
    return f"{sign}{symbol}{number}"


def plural(label: str, quantity=None) -> str:
    if quantity == 1 or label.endswith("s"):
        return label
    return label + "s"


def period(offer: dict) -> tuple:
    interval = offer.get("interval")
    return (interval, offer.get("interval_count", 1) if interval else 1)


def period_suffix(offer: dict) -> str:
    interval, count = period(offer)
    if interval is None:
        return " one-time"
    short = PERIOD_SHORT[interval]
    return f"/{short}" if count == 1 else f" every {count} {short}"


def tidy(value):
    """45000.0 -> 45000, so JSON output reads like the input."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def annualized(offer: dict | None):
    """Yearly value of a recurring offer; None for a one-time fee."""
    if not offer:
        return None
    interval, count = period(offer)
    if interval is None:
        return None
    return tidy(round(offer["amount"] * PER_YEAR[interval] / count, 2))


def card_text(ev: dict, currency: str = "usd") -> str:
    title = ev["title"].strip()
    offers = event_offers(ev)
    if len(offers) == 1:
        amount = money(offers[0]["amount"], currency)
        if amount not in title:
            suffix = "" if period(offers[0]) in (("year", 1), (None, 1)) else period_suffix(offers[0])
            title = f"{title} = {amount}{suffix}"
    kind = kind_of(ev)
    if kind == "acceptance" and "✅" not in title:
        title = f"{title} ✅"
    if kind == "blocker" and ev.get("resolved"):
        title = f"{title.replace('⚠️', '').strip()} · resolved {fmt_day(ev['resolved'])}"
    elif kind == "blocker" and "⚠️" not in title:
        title = f"⚠️ {title}"
    return "\n".join([f"**{title}**", *detail_lines(ev)])


# ---------------------------------------------------------------- the deal

def currency_of(data: dict) -> str:
    return data.get("currency", "usd").lower()


def unit_of(data: dict) -> str:
    return data.get("unit_label", "seat")


def final_offer(data: dict) -> dict | None:
    """The accepted offer: on the acceptance event, or the last offer before it."""
    latest = None
    for ev in data["events"]:
        offers = event_offers(ev)
        if ev.get("kind") == "acceptance":
            return offers[0] if offers else latest
        if offers:
            latest = offers[-1]
    return None


def pricing_rows(data: dict) -> list:
    """Current contract first, then one row per offer in event order. The accepted one is final."""
    rows = []
    previous = (data.get("contract") or {}).get("previous")
    if previous:
        rows.append({"date": "Current", "from": "Contract", "offer": previous, "final": False})
    for ev in data["events"]:
        who = data["vendor"] if ev["side"] == "vendor" else data["customer"]
        offers = event_offers(ev)
        for offer in offers:
            rows.append({"date": fmt_day(ev["date"]), "from": who, "offer": offer, "final": False})
        if ev.get("kind") == "acceptance" and len(rows) > (1 if previous else 0):
            rows[-1].update(date=f"{fmt_day(ev['date'])} ✅", **{"from": "Final", "final": True})
            break
    return rows


def pricing_table(data: dict) -> dict:
    currency, unit = currency_of(data), unit_of(data)
    rows = pricing_rows(data)
    periods = {period(r["offer"]) for r in rows}
    header = AMOUNT_HEADER.get(next(iter(periods))) if len(periods) == 1 else None

    def cell(value):
        if value is None:
            return ""
        if is_number(value):
            return f"{value:,g}"
        return str(value)

    body = []
    for r in rows:
        offer = r["offer"]
        price = offer.get("unit_price")
        amount = money(offer["amount"], currency) + ("" if header else period_suffix(offer))
        body.append([r["date"], r["from"], cell(offer.get("quantity")),
                     money(price, currency) if is_number(price) else cell(price), amount])
    final = [i for i, r in enumerate(rows) if r["final"]]
    return {"columns": ["Date", "From", plural(unit[:1].upper() + unit[1:]), "Price", header or "Amount"],
            "rows": body, "final_row": final[0] if final else None}


def table_height(n_rows: int) -> int:
    return TABLE_ROW_H * (n_rows + 1)


TABLE_ID = "<id of the table the first call adds>"


def table_op(table: dict) -> dict:
    """The `add` operation for the pricing table. Cell text is Markdown, so escape what it reads."""
    def md(text):
        return re.sub(r"([*_~`|\[\]\\])", r"\\\1", text)

    rows = [[md(c) for c in row] for row in table["rows"]]
    if table["final_row"] is not None:
        # Styled inline: the `styles` map is refused by the MCP ("Could not parse edn body").
        rows[table["final_row"]] = [{"text": c, **FINAL_ROW_STYLE} for c in rows[table["final_row"]]]
    # No x/y: where Whimsical puts a new table doesn't follow them, so it's moved in a second call.
    return {"op": "add", "type": "table",
            "columns": [{"header": h, "width": w} for h, w in zip(table["columns"], TABLE_WIDTHS)],
            "rows": rows}


def deal(data: dict) -> dict:
    """Old and new terms, annualized, for the subtitle and the write-up."""
    contract = data.get("contract") or {}
    previous = contract.get("previous")
    new = contract.get("new") or final_offer(data)
    result = {"currency": currency_of(data), "previous": previous, "new": new,
              "previous_annual": annualized(previous), "new_annual": annualized(new),
              "change": None, "change_pct": None, "nrr_pct": None}
    if result["previous_annual"] and result["new_annual"] is not None:
        change = result["new_annual"] - result["previous_annual"]
        result["change"] = tidy(round(change, 2))
        result["change_pct"] = round(100 * change / result["previous_annual"], 1)
        result["nrr_pct"] = round(100 * result["new_annual"] / result["previous_annual"], 1)
    return result


def terms_text(offer: dict, data: dict) -> str:
    currency, unit = currency_of(data), unit_of(data)
    quantity, price = offer.get("quantity"), offer.get("unit_price")
    parts = []
    if is_number(quantity):
        parts.append(f"{quantity:,g} {plural(unit, quantity)}")
    elif quantity:
        parts.append(f"{quantity} {plural(unit)}")
    if is_number(price):  # text prices like "Flat" or tiers stay in the table
        parts.append(f"at {money(price, currency)}")
    amount = money(offer["amount"], currency) + period_suffix(offer)
    return f"{' '.join(parts)} for {amount}" if parts else amount


def span_text(data: dict) -> str:
    first, last = data["events"][0]["date"], data["events"][-1]["date"]
    d1, d2 = date.fromisoformat(first), date.fromisoformat(last)
    if d1.year == d2.year:
        return f"{fmt_day(first)} to {fmt_day(last)}, {d2.year}"
    return f"{fmt_day(first)}, {d1.year} to {fmt_day(last)}, {d2.year}"


def subtitle_text(data: dict) -> str:
    parts = [span_text(data)]
    d = deal(data)
    if d["previous"] and d["new"]:
        terms = f"{terms_text(d['previous'], data)} → {terms_text(d['new'], data)}"
        if d["change_pct"] is not None:
            terms += f" ({'+' if d['change_pct'] > 0 else ''}{d['change_pct']:g}%)"
        parts.append(terms)
    elif d["previous"]:
        parts.append(f"Currently {terms_text(d['previous'], data)}")
    parts.append(f"Contract expiry {fmt_day(data['expiry_date'])}")
    return " · ".join(parts)


def year_of(data: dict) -> int:
    return data.get("year") or date.fromisoformat(data["expiry_date"]).year


# ---------------------------------------------------------------- layout

def phase_color(name: str, is_last: bool) -> str:
    """Purple, except a final phase that closes the deal."""
    words = set(re.findall(r"[a-z]+", name.lower()))
    return CLOSE_PHASE_COLOR if is_last and words & set(CLOSE_WORDS) else PHASE_COLOR


def shape(shape_type, x, y, w, h, text, color, deco="fill", **extra):
    op = {"op": "add", "type": "shape", "shape_type": shape_type, "x": x, "y": y,
          "width": w, "height": h, "color": color, "deco": deco, "text": text}
    op.update(extra)
    return op


def layout(data: dict, count: int | None = None) -> dict:
    """Where everything goes for the first `count` events (all by default).

    The expiry marker sits at its date: after the last event on or before it, taking one row, so
    events after the contract ended (a late signature) come below it. Returns the ops tagged with
    the event they belong to, the banners, the marker's y and where the center line ends.
    """
    events = data["events"][:len(data["events"]) if count is None else count]
    currency, last_phase = currency_of(data), phase_label(data["events"][-1]["phase"])
    expiry = data["expiry_date"]
    items, banners = [], []
    phase, number, last_y, expiry_y = None, 0, None, None
    for i, ev in enumerate(events):
        if expiry_y is None and last_y is not None and ev["date"] > expiry:
            expiry_y = last_y + EXPIRY_GAP
            last_y += STEP
        name = phase_label(ev["phase"])
        if name != phase:
            number += 1
            banner_y = 0 if last_y is None else last_y + CARD_H + 20
            color = phase_color(name, name == last_phase)
            banners.append({"event": i, "text": f"Phase {number} · {name}", "color": color, "y": banner_y})
            items.append((i, shape("rect", 0, banner_y, WIDTH, BANNER_H, f"Phase {number} · {name}", color)))
            y = banner_y + BANNER_TO_CARD
            phase = name
        else:
            y = last_y + STEP
        color, deco = style_of(ev)
        x = VENDOR_X if ev["side"] == "vendor" else CUSTOMER_X
        items.append((i, shape("rect", x, y, CARD_W, CARD_H, card_text(ev, currency), color, deco,
                               font_size="s", text_align="left")))
        items.append((i, shape("pill", PILL_X, y + PILL_DY, PILL_W, PILL_H, fmt_day(ev["date"]), "silver",
                               font_size="s")))
        last_y = y
    if expiry_y is None:
        expiry_y = (last_y if last_y is not None else -STEP) + EXPIRY_GAP
    line_end = max(expiry_y + LINE_TAIL, (last_y if last_y is not None else 0) + CARD_H + LINE_TAIL)
    return {"items": items, "banners": banners, "expiry_y": expiry_y, "line_end": line_end, "last_y": last_y}


def expiry_op(data: dict, y: int) -> dict:
    return shape("pill", EXPIRY_X, y, EXPIRY_W, EXPIRY_H, expiry_text(data), "red", font_size="s")


def title_size(text: str) -> tuple:
    """(font size, line height) that keeps the title on one line."""
    for font, height, chars in TITLE_SIZES:
        if len(text) <= chars:
            return font, height
    return TITLE_SIZES[-1][:2]


def header_ys(n_table_rows: int, title_h: int = TITLE_SIZES[0][1]) -> dict:
    """Top y of each header element, stacked upwards from the legends."""
    table_y = LEGEND_Y - TABLE_GAP - table_height(n_table_rows) if n_table_rows else None
    subtitle_y = (table_y if table_y is not None else LEGEND_Y) - SUBTITLE_GAP - SUBTITLE_H
    return {"table": table_y, "subtitle": subtitle_y, "title": subtitle_y - TITLE_GAP - title_h}


def title_text(data: dict) -> str:
    return data.get("title") or f"{data['customer']} {year_of(data)} Renewal Timeline"


def expiry_text(data: dict) -> str:
    return f"{fmt_day(data['expiry_date'])} · Contract expiry"


def build_new(data: dict) -> tuple:
    """Return (operations, table y or None)."""
    table = pricing_table(data)
    font, height = title_size(title_text(data))
    ys = header_ys(len(table["rows"]), height)
    ops = [
        {"op": "add", "type": "text", "x": 0, "y": ys["title"], "width": WIDTH,
         "color": "default", "font_size": font, "text": title_text(data)},
        {"op": "add", "type": "text", "x": 0, "y": ys["subtitle"], "width": WIDTH, "height": SUBTITLE_H,
         "color": "default", "font_size": "s", "text": subtitle_text(data)},
    ]
    if table["rows"]:
        ops.append(table_op(table))
    ops += [
        shape("rect", 0, LEGEND_Y, LEGEND_W, LEGEND_H, data["vendor"], "blue", font_size="s"),
        shape("rect", WIDTH - LEGEND_W, LEGEND_Y, LEGEND_W, LEGEND_H, data["customer"], "orange", font_size="s"),
    ]
    plan = layout(data)
    # Center line first so it renders beneath cards and pills.
    ops.append(shape("rect", LINE_X, 0, LINE_W, plan["line_end"], "", "silver"))
    ops.extend(op for _, op in plan["items"])
    ops.append(expiry_op(data, plan["expiry_y"]))
    return ops, ys["table"] if table["rows"] else None


# ---------------------------------------------------------------- reading a board back

BOARD_COLUMNS = "type,id,parentId,x,y,width,height,color,locked,text"


def listing_rows(raw: str) -> list:
    """Object rows from a saved `fetch` (detail: detailed): the JSON reply, or just its text."""
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            text = data["text"]
        elif isinstance(data, dict) and isinstance(data.get("content"), list):
            text = "\n".join(c.get("text", "") for c in data["content"] if isinstance(c, dict))
            inner = text.strip()
            if inner.startswith("{"):
                return listing_rows(inner)
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(BOARD_COLUMNS))
    except StopIteration:
        sys.exit("No `type,id,parentId,x,y,...` header in the board listing. "
                 "Save the result of fetch with detail: \"detailed\".")
    rows = []
    for line in lines[start + 1:]:
        if not line.strip() or line.startswith("Palette"):
            break
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        row = dict(zip(BOARD_COLUMNS.split(","), parts))
        try:
            for key in ("x", "y", "width", "height"):
                row[key] = float(row[key])
        except ValueError:
            continue
        props = re.search(r"\[props: (\{.*?\})\]", row["text"])
        row["font_size"] = json.loads(props.group(1)).get("font_size") if props else None
        row["text"] = re.sub(r"( \[(props|url|label): .*?\])+$", "", row["text"])
        rows.append(row)
    return rows


def read_calls(data: dict, board_id: str) -> list:
    """The fetch calls whose replies --append needs, as small as the file allows."""
    if not isinstance(data.get("board"), dict) or "events" not in data["board"]:
        # No record of what's on the board (one made before --done existed): read all of it.
        return [{"tool": "fetch", "arguments": {"id": board_id, "detail": "detailed", "limit": 200,
                                                "spatial": False}}]
    drawn = data["events"][:data["board"]["events"]]
    resolved = [ev["title"].replace("⚠️", "").strip() for ev in drawn if ev.get("resolved")]
    return [
        {"tool": "fetch", "arguments": {"id": board_id, "detail": "detailed", "spatial": False,
                                        "grep_text": ["Contract expiry", "Phase ", *resolved][:20]}},
        {"tool": "fetch", "arguments": {"id": board_id, "detail": "detailed", "spatial": False,
                                        "select_kinds": ["text", "table"]}},
    ]


def read_board(paths: list) -> dict:
    """The parts of an existing timeline the script needs, found by their size and text."""
    raws = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                raws.append(f.read())
        except FileNotFoundError:
            sys.exit(f"{path}: file not found")
    rows = [row for raw in raws for row in listing_rows(raw)]
    for raw in raws:
        if re.search(r'"(next_)?cursor"\s*:\s*"[^"]+"', raw) or re.search(r"Showing \d+ of \d+", raw):
            sys.exit("A board listing has more pages. Fetch again with the cursor it gives, save every page, "
                     "and pass them all to --append.")
    seen, unique = set(), []
    for row in rows:  # the two reads overlap (the subtitle is in both)
        if row["id"] not in seen:
            seen.add(row["id"])
            unique.append(row)
    rows = unique

    def find(kind, w=None, h=None, text=None):
        return [r for r in rows if r["type"] == kind
                and (w is None or r["width"] == w) and (h is None or r["height"] == h)
                and (text is None or re.search(text, r["text"]))]

    cards = sorted(find("shape:rect", CARD_W, CARD_H), key=lambda r: r["y"])
    banners = find("shape:rect", WIDTH, BANNER_H, r"^Phase \d+ · ")
    expiry = find("shape:pill", EXPIRY_W, text="Contract expiry")
    line = find("shape:rect", LINE_W)
    subtitle = find("text", text="Contract expiry")
    title = [r for r in rows if r["type"] == "text" and r["font_size"] in {f for f, _, _ in TITLE_SIZES}
             and "Contract expiry" not in r["text"]] or find("text", text="Renewal Timeline")
    tables = sorted(find("table"), key=lambda r: r["y"])
    missing = [name for name, found in (("phase banners", banners), ("expiry marker", expiry)) if not found]
    if missing:
        sys.exit(f"This doesn't look like a renewal timeline board: no {', '.join(missing)} found.")
    return {"cards": cards, "banners": {b["text"]: b for b in banners}, "expiry": expiry[0],
            "line": line[0] if line else None, "subtitle": subtitle[0] if subtitle else None,
            "title": title[0] if title else None, "table": tables[0] if tables else None,
            "complete": bool(line)}  # a full read has the center line; the small one doesn't


def plain(text: str) -> str:
    """Card text as fetch prints it: no markers or bold, line breaks read as spaces."""
    return " ".join(re.sub(r"\*\*|✅|⚠️", " ", text).split())


def events_on_board(data: dict, board: dict, warnings: list) -> int:
    recorded = data.get("board", {}).get("events") if isinstance(data.get("board"), dict) else None
    if board["complete"]:
        count = len(board["cards"])
        if recorded is not None and recorded != count:
            warnings.append(f"events.json says {recorded} events are on the board, but it has {count} cards; "
                            f"using {count}")
        return count
    if recorded is None:
        sys.exit("events.json doesn't say how many events are on the board (board.events), so read the whole "
                 "board: fetch with detail \"detailed\" and limit 200, and pass that to --append.")
    return recorded


def build_append(data: dict, board: dict, warnings: list) -> tuple:
    """Return (operations, table y or None, how many new events) for a board read with read_board."""
    events = data["events"]
    already = events_on_board(data, board, warnings)
    if already > len(events):
        sys.exit(f"The board has {already} events but events.json has {len(events)}. "
                 "Keep every event in events.json, old and new.")
    old, new = layout(data, already), layout(data)

    # Is the board what the first `already` events would draw? If not, someone edited it.
    if board["complete"]:
        for i, (card, ev) in enumerate(zip(board["cards"], events)):
            if not plain(card["text"]).startswith(plain(ev["title"].replace("⚠️", ""))):
                warnings.append(f"board card {i + 1} reads {plain(card['text'])[:50]!r} but events[{i}] is "
                                f"{ev['title']!r}: the board was edited, or events.json changed order")
                break
    if board["expiry"]["y"] != old["expiry_y"] or any(
            b["text"] not in board["banners"] or board["banners"][b["text"]]["y"] != b["y"] for b in old["banners"]):
        warnings.append("the board's phase banners or expiry marker aren't where the first "
                        f"{already} events put them: it was edited by hand, or made by an older version")

    ops = []
    if board["line"] is None:
        # The small read doesn't find the center line (it has no text): extend it with a segment.
        start = old["line_end"]
        if new["expiry_y"] == old["expiry_y"] and new["expiry_y"] <= start < new["expiry_y"] + EXPIRY_H:
            start = new["expiry_y"] + EXPIRY_H  # under the marker, which stays on top
        if new["line_end"] > start:
            ops.append(shape("rect", LINE_X, start, LINE_W, new["line_end"] - start, "", "silver"))
    else:
        ops.append({"op": "update", "id": board["line"]["id"], "height": new["line_end"]})
    ops.extend(op for i, op in new["items"] if i >= already)

    # The old last phase turns purple once a phase follows it.
    for b in new["banners"]:
        shown = board["banners"].get(b["text"])
        if b["event"] < already and shown and shown["color"].lower() != {"dark-purple": "purple",
                                                                          "green": "mint"}[b["color"]]:
            ops.append({"op": "update", "id": shown["id"], "color": b["color"]})

    # Blockers resolved since they were drawn.
    for i, ev in enumerate(events[:already]):
        if not ev.get("resolved"):
            continue
        key = plain(ev["title"].replace("⚠️", ""))
        rows = [r for r in board["cards"] if plain(r["text"]).startswith(key)]
        if not rows:
            warnings.append(f"events[{i}] is resolved, but its card {ev['title']!r} wasn't in the board listing")
        elif "resolved" not in rows[0]["text"]:
            color, deco = style_of(ev)
            ops.append({"op": "update", "id": rows[0]["id"], "text": card_text(ev, currency_of(data)),
                        "color": color, "deco": deco})

    # The expiry marker moves to its row; re-added rather than moved so it stays above the line.
    if new["expiry_y"] != board["expiry"]["y"]:
        ops.append(expiry_op(data, new["expiry_y"]))
        ops.append({"op": "delete", "id": board["expiry"]["id"]})
    elif board["expiry"]["text"] != expiry_text(data):
        ops.append({"op": "update", "id": board["expiry"]["id"], "text": expiry_text(data)})

    table = pricing_table(data)
    old_table = board["table"]
    new_events = events[already:]
    prices_changed = any(event_offers(ev) or ev.get("kind") == "acceptance" for ev in new_events)
    if table["rows"] and (prices_changed or not old_table):
        bottom = old_table["y"] + old_table["height"] if old_table else LEGEND_Y - TABLE_GAP
        table_y = int(bottom - table_height(len(table["rows"])))
        if old_table:
            ops.append({"op": "delete", "id": old_table["id"]})
        ops.append(table_op(table))
        shift = table_y - (int(old_table["y"]) if old_table else header_ys(0)["subtitle"] + SUBTITLE_H + SUBTITLE_GAP)
    else:
        table_y, shift = None, 0
    subtitle = board["subtitle"]
    if subtitle is not None:
        update = {"op": "update", "id": subtitle["id"]}
        if shift:
            update["y"] = int(subtitle["y"] + shift)
        if subtitle["text"] != subtitle_text(data):
            update["text"] = subtitle_text(data)
        if len(update) > 2:
            ops.append(update)
    title = board["title"]
    if title is not None:
        # The title sits on the subtitle, sized to stay on one line: fix it if it doesn't.
        font, height = title_size(title_text(data))
        base = subtitle["y"] + shift if subtitle is not None else title["y"] + shift + height + TITLE_GAP
        update = {"op": "update", "id": title["id"]}
        if title["y"] != base - TITLE_GAP - height:
            update["y"] = int(base - TITLE_GAP - height)
        if title["text"] != title_text(data):
            update["text"] = title_text(data)
        if title["font_size"] != font:
            update["font_size"] = font
        if len(update) > 2:
            ops.append(update)
    return ops, table_y, len(new_events)


def edit_calls(board_id: str, operations: list, table_y) -> dict:
    """The edit call to make, and the table move to make after it, once you have the table's id."""
    result = {"tool": "edit", "arguments": {"id": board_id, "operations": operations}}
    if table_y is not None:
        result["then"] = {"tool": "edit", "arguments": {"id": board_id, "operations": [
            {"op": "update", "id": TABLE_ID, "x": 0, "y": table_y}]}}
    return result


def record_board(path: str, data: dict, board_id: str) -> None:
    """Note in events.json which board shows it and how many of its events are drawn."""
    board = data.get("board") if isinstance(data.get("board"), dict) else {}
    board.update(id=board_id, url=f"https://whimsical.com/{board_id}", events=len(data["events"]))
    data["board"] = board
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("events")
    p.add_argument("--check", action="store_true", help="Only check events.json and print the deal numbers")
    p.add_argument("--board-id", help="The board to draw on (from create_file, or the board's link)")
    p.add_argument("--read", action="store_true", help="Print the fetch calls --append needs")
    p.add_argument("--append", nargs="+", metavar="BOARD_JSON", help="The saved replies of those fetch calls")
    p.add_argument("--done", action="store_true",
                   help="After the board is drawn and checked: record it in events.json")
    args = p.parse_args()

    try:
        with open(args.events, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit(f"{args.events}: file not found")
    except json.JSONDecodeError as e:
        sys.exit(f"{args.events}: not valid JSON (line {e.lineno}, column {e.colno}: {e.msg})")

    problems = validate(data)
    for w in problems.warnings:
        print(f"warning: {w}", file=sys.stderr)
    if problems.errors:
        n = len(problems.errors)
        sys.exit(f"{args.events} has {n} problem{'s' if n > 1 else ''}:\n  " + "\n  ".join(problems.errors))

    if args.check:
        print(json.dumps({"ok": True, "events": len(data["events"]), "warnings": len(problems.warnings),
                          "deal": deal(data), "pricing_rows": len(pricing_rows(data))},
                         indent=2, ensure_ascii=False))
        return
    recorded = data["board"].get("id") if isinstance(data.get("board"), dict) else None
    board_id = args.board_id or recorded
    if not board_id:
        sys.exit("--board-id is required: create the board first, or take the id from its link")
    # Accept a bare id or a board link (https://whimsical.com/<slug>-<id>?ref=mcp).
    board_id = board_id.split("?")[0].rstrip("/").split("/")[-1].split("-")[-1]
    if args.done:
        record_board(args.events, data, board_id)
        print(f"Recorded in {args.events}: board {board_id} shows its {len(data['events'])} events.")
        return
    if args.read:
        print(json.dumps(read_calls(data, board_id), ensure_ascii=False))
        return
    if args.append:
        warnings: list = []
        operations, table_y, added = build_append(data, read_board(args.append), warnings)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"{added} new event{'s' if added != 1 else ''} to add", file=sys.stderr)
    else:
        operations, table_y = build_new(data)
    print(json.dumps(edit_calls(board_id, operations, table_y), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Output piped into `head` or similar, which stopped reading: not an error.
        sys.stderr.close()
        sys.exit(0)
