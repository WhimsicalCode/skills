# Renewal summary template

Use this structure: prose and short bullets, bold section labels. If `as_of` is more than a week old, say so in the first line, so nobody takes old numbers for current ones. When updating a write-up that already exists, edit the sections the new events change, in place, and say what changed under **Timeline updates**. Replace `<unit>` with the `unit_label` from `events.json` ("seats", "Editors", and so on) and capitalize it consistently.

---

**<Customer> <Year> Renewal Summary**

**Deal terms (agreed <date>)**: old terms → new terms, rate per <unit>, term length, overage rate, renewal cap, any clauses removed or added. If not agreed yet, label it "Current proposal" and say where it stands.

**NRR: X%** (new ARR / old ARR). Take the numbers from the `deal` that `build_board.py --check` prints, so they match the board. State the dollar and percent change. If the terms aren't recurring (a project fee), skip NRR and give the change in value instead. If there's no expansion, note that GRR equals NRR. Mention the path back up (overage rate, expansion clause) if relevant.

**<Unit> usage (current <unit>, as of <usage.as_of>)**:

| Metric | Count | % of current <unit> |
|---|---|---|
| Current <unit> | N | 100% |
| **Active last 90 days** | **N** | **X%** |
| Active last 30 days | N | X% |

Then one or two sentences on removed-but-active members and headroom versus the contracted number.

If `events.json` has no `usage`, replace this section with one line saying usage wasn't checked, and where the numbers could come from (an admin dashboard, a BI tool).

**The reduction** (only if the billable count dropped): what the customer said versus what the data shows, with dates and counts.

**Negotiation path**: numbered list of each offer and counter in order (the events with an `offer`), with who made it and the amount.

**Status and open items**: PO, order form or quote, signature status, and the expiry date. Bold the open item if the renewal isn't signed yet and the contract expires within a week, or has already expired.

**Timeline updates**: what was added or changed on the board, with a link to it. If Whimsical wasn't connected, say the board wasn't built and how to connect it.

**Assumptions**: only if you made any (an inferred company name or domain, a missing data source). One line each.
