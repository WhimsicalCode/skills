# events.json schema

One file describes the deal: who the two companies are, what each side said and offered, and,
optionally, the contract terms and usage numbers. `<this skill's folder>/scripts/build_board.py` checks it, builds the
board from it, and computes the deal numbers the write-up uses. A full example is in
`examples/events.example.json`.

Check a file at any time:

```
python3 <this skill's folder>/scripts/build_board.py events.json --check
```

It lists every problem at once, each with where it is (`events[12].date: ...`), so you can fix them
all in one pass. Warnings (a title that may not fit a card, an amount that doesn't match quantity ×
price) don't stop the build. Fields not described here are allowed and ignored.

Two examples, both fictional: `examples/events.example.json` is small and shows the shape;
`examples/full-deal.example.json` is a whole renewal (22 events, a negotiation with 7 offers,
usage and a resolved blocker).

```json
{
  "customer": "Globex",
  "vendor": "Acme",
  "currency": "usd",
  "unit_label": "seat",
  "expiry_date": "2026-11-30",
  "contract": {
    "previous": {"quantity": 120, "unit_price": 480, "amount": 57600, "interval": "year"}
  },
  "usage": {"as_of": "2026-11-04", "source": "Admin dashboard export",
            "current": 104, "active_90d": 96, "active_30d": 88, "active_removed": 3},
  "open_items": ["PO not issued yet; contract expires Nov 30"],
  "events": [
    {"date": "2026-09-22", "side": "customer", "phase": "Negotiation",
     "title": "Asks for 90 seats at $456", "detail": "Wants a lower rate for a smaller team",
     "offer": {"quantity": 90, "unit_price": 456, "amount": 41040, "interval": "year"}},
    {"date": "2026-10-20", "side": "customer", "kind": "acceptance", "phase": "Negotiation",
     "title": "Accepts 100 seats at $504", "detail": "Procurement to issue PO",
     "offer": {"quantity": 100, "unit_price": 504, "amount": 50400, "interval": "year"}}
  ]
}
```

## Top level

| Field | Required | Notes |
|---|---|---|
| customer | yes | The customer's name. |
| vendor | yes | The user's company. |
| expiry_date | yes | Date the current contract ends (`2026-11-30`). |
| events | yes | What happened, oldest first. See below. |
| currency | no | Three-letter code, lowercase: `usd` (default), `eur`, `gbp`… |
| unit_label | no | What one paid unit is called, singular: `seat` (default), `Editor`, `license`, `day`. Used in the table header and the subtitle. |
| year | no | Renewal year for the title. Defaults to the year of `expiry_date`. |
| title | no | The heading on the board. Defaults to "<customer> <year> Renewal Timeline". |
| as_of | no | When the file was last brought up to date. |
| contract | no | `previous`: the terms being renewed. `new`: the agreed terms, plus `agreed` (a date) and any `note`. Both use the price shape below. `new` defaults to the accepted offer, so you only need it for terms the offers don't show. |
| usage | no | See below. Without it, the write-up says usage wasn't checked. |
| open_items | no | Short sentences: what's still missing (signature, PO, a billing change). |
| people | no | `[{"name", "role", "company"}]`, for the write-up. |
| board | no | `{"id", "url", "events"}`: the board this file feeds, and how many of its events are drawn on it. `build_board.py --done` writes it; don't edit `events` by hand. |

## Events

| Field | Required | Notes |
|---|---|---|
| date | yes | `2026-10-27`. Events must be in date order; same-day events keep the order you give them. |
| side | yes | `vendor` (left on the board) or `customer` (right). |
| phase | yes | A short name like `Negotiation`. Each phase must be one unbroken run of events. The board numbers them ("Phase 3 · Negotiation"), so don't include the number. |
| title | yes | Under ~50 characters, shown in bold. When the event has one offer, the board adds its amount (" = $48,000") unless the title already shows it. |
| detail | no | One short line, or a list of up to 3 short lines. |
| kind | no | Changes the card color. Leave it out for ordinary messages. See below. |
| offer | no | The price this event proposes, accepts or confirms: one price object, or a list when a message offers several options. These build the pricing table. |
| people | no | Who took part, for the write-up: `["Dana Ruiz (IT Director)"]`. |
| resolved | no | For a `blocker`: the date it was settled. The card turns to an outline and its title says "resolved <date>". |
| source | no | Where it came from (`{"tool": "gmail", "thread_id": "..."}`, or `{"tool": "user"}` for what the user told you), so a card can be traced back. Never shown on the board. |

**`kind`**

| kind | Use for | Card |
|---|---|---|
| (left out) | Ordinary messages | Blue outline (vendor) or orange outline (customer) |
| `milestone` | Key moments: the vendor's final offer, order form sent or countersignature; the customer's PO issued or contract signed | Filled: blue (vendor) or orange (customer) |
| `acceptance` | The customer accepts. At most one. | Green, ✅ added to the title |
| `blocker` | An open item or risk: missing PO, legal hold, security review. Either side. | Yellow, ⚠️ added to the title; a yellow outline once `resolved` |

`routine` and `customer` are also accepted; they're the defaults for each side.

## Prices

Used by `offer`, `contract.previous` and `contract.new`. The names follow Stripe's prices, but
amounts are in whole currency units (`45000` means $45,000), not cents.

| Field | Required | Notes |
|---|---|---|
| amount | yes | The total for one interval, as a number. The one number that makes every offer comparable. |
| interval | no | `year`, `month`, `week` or `day`. Leave it out for a one-time fee (a project, a setup fee). |
| interval_count | no | How many intervals the amount covers. Defaults to 1; `month` + `3` is quarterly. |
| quantity | no | How many units: a number, or text like `"Unlimited"`. |
| unit_price | no | Price per unit per interval: a number, or text when it isn't one number (`"$180 first 100, then $150"`, `"20% off list"`). |
| note | no | Anything else worth a word: term length, overage rate, what a fee covers. |

Examples:

| Deal | Price |
|---|---|
| 250 seats at $180 a year | `{"quantity": 250, "unit_price": 180, "amount": 45000, "interval": "year"}` |
| Unlimited plan | `{"quantity": "Unlimited", "amount": 60000, "interval": "year"}` |
| Tiered | `{"quantity": 320, "unit_price": "$180 first 100, then $150", "amount": 51000, "interval": "year"}` |
| Monthly retainer | `{"amount": 20000, "interval": "month"}` |
| Fixed-fee project | `{"amount": 400000, "note": "6-month project"}` |

**The pricing table** is built from these: the current contract first (`contract.previous`), then
one row per offer in event order. The accepted offer becomes the final row (marked ✅): the
acceptance event's own `offer` if it has one, otherwise the last offer before it. Offers after
the acceptance aren't shown. When every row has the same interval, the last column is named after
it ("Annual", "Monthly", "Total" for one-time fees); otherwise each amount shows its own
("$3,420/mo").

**The deal numbers** (`--check` prints them as `deal`): old and new terms, both annualized, the
change in amount and percent, and NRR. They're only computed when both the old and new terms are
recurring; a one-time fee has no annual value to compare.

## Usage

All fields are optional. Counts are whole numbers.

| Field | Notes |
|---|---|
| as_of, source | When and where the numbers come from ("Admin dashboard export", "BI, queried Nov 5"). |
| current | Paid units in use now. |
| active_90d, active_30d | Of those, how many were active in the last 90 / 30 days. |
| active_removed | Removed in the last 90 days even though they had been active. |

Anything else you know (viewers, removals by date, peak usage) can go in `usage` under any name;
the write-up quotes it as is.

## Writing events

- One event per meaningful step, not per email. Three back-and-forth emails scheduling a call are one event.
- Auto-replies, calendar invites and internal-only notes are usually not events, but an internal note that records a decision ("legal approved the MSA") can be.
- Put a price on every event that proposes one, including the customer's asks. That's what fills the pricing table and the negotiation path.
- If you only have a CRM activity log without message bodies, events can come from logged calls, meetings and stage changes too.
