# Timeline board layout

`<this skill's folder>/scripts/build_board.py` implements this spec and writes the Whimsical calls, so you don't compute coordinates yourself. Read this to check a board against what it should look like, or to understand a change.

All coordinates are top-left x, y, as `fetch` reports them. The board is 1040 wide. The vendor (the user's company) is on the left, the customer on the right, with a vertical center line and date pills down the middle. Colors are Whimsical color keys; `fetch` shows their names (`dark-purple` reads as "Purple", `green` as "Mint", `default` as "Slate").

```
              <Customer> <Year> Renewal Timeline
     <dates> · <old terms> → <new terms> (<change>) · Contract expiry <date>
 | Date | From | <Units> | Price | Annual |
 | ...  pricing table, the agreed row in green ...  |
 [Vendor legend]                               [Customer legend]
 ============ Phase 1 · Finding the owner ===================
 [ vendor card ]      ( Aug 11 )
                      ( Aug 14 )       [ customer card ]
 [ vendor card ]      ( Aug 20 )
 ============ Phase 2 · ... =================================
                         |
                  ( Nov 30 · Contract expiry )
```

## Header (above y = 0)

Stacked upwards from the legends, so a taller pricing table pushes the subtitle and title up, never the timeline down.

| Element | Type | x, y | w x h | Style | Text |
|---|---|---|---|---|---|
| Title | text | 0, its bottom 8 above the subtitle | 1040 wide, one line | default, font l3 (72 tall) up to 36 characters, l2 (48) up to 56, else l1 (36) | `title`, or "<Customer> <Year> Renewal Timeline" |
| Subtitle | text | 0, table y - 60 | 1040 x 20 | default, font s | "<first event> to <last event>, <year> · <old terms> → <new terms> (<% change>) · Contract expiry <date>" |
| Pricing table | table | 0, -120 - its height | 1040 x 40 per row, header included | header default fill, body outline | Columns: Date, From, <Units>, Price, Annual (or Monthly, Total, Amount) |
| Legend: vendor | rect | 0, -80 | 200 x 40 | blue, fill, font s | "<Vendor>" |
| Legend: customer | rect | 840, -80 | 200 x 40 | orange, fill, font s | "<Customer>" |

With the example's 4 rows: table at y -320, subtitle -380, title -460. An update puts the title back on its line if it was moved or resized. Without any prices there's no table, and the subtitle sits 40 above the legends.

Pricing table rows come from the events' offers (see `event-schema.md`): first "Current | Contract | ...", then one row per offer with its date and who made it. The accepted row reads "<date> ✅ | Final", in green and bold. Column widths 140, 180, 140, 330, 240; Whimsical adds 10 of border.

Whimsical doesn't put a new table where `x` and `y` say, and won't move a table in the call that creates it, so the script adds it unplaced and a second call (`then`) moves it.

## Center line

rect, x 517, y 0, width 6, silver, fill. It ends 40 below whichever is lower: the expiry marker's top, or the last card's bottom. Drawn first, so cards and pills sit on top of it. An update that can't see the line (the short read doesn't include it) adds a segment below it instead of resizing it.

## Phase banners

rect, x 0, width 1040, height 50, fill. Text "Phase N · <Name>".

- Color: `dark-purple`, except the last phase when it closes the deal (its name has the word close, closed, signed or won): `green`. Appending a phase after it turns it back to `dark-purple`.
- First banner at y 0. A new banner goes 20px below the previous card's bottom (card_y + 140). The first card after a banner goes at banner_y + 80.

## Event cards

Every event is one card plus one date pill on the same row.

- Card: rect, 420 x 120, font s, left-aligned. Text "**<Title>**" then one line per detail line. A single offer adds " = <amount>" to the title.
  - Vendor events: x 0. Customer events: x 620.
- Date pill: pill, x 460, y = card_y + 40, 120 x 40, silver, fill, font s. Text like "Oct 29".
- Vertical step: next card y = previous card y + 140. Keep the step even when consecutive events are on the same side; the rhythm is what makes the timeline readable.

## Card colors

| kind | color | deco |
|---|---|---|
| (default, vendor) outreach, replies | blue | outline |
| milestone, vendor (final offer, order form sent) | blue | fill |
| milestone, customer (PO issued, contract signed) | orange | fill |
| (default, customer) message, ask, counter | orange | outline |
| acceptance (✅ in title) | green | fill |
| blocker (⚠️ in title) | yellow | fill |
| blocker, resolved ("resolved <date>" in title) | yellow | outline |

## Expiry marker

pill, x 400, 240 x 50, red, fill, font s. Text "<Mon D> · Contract expiry".

It sits at its date: y = (last card on or before the expiry date) y + 160, and it takes one row of the rhythm, so events after the contract ended (a late signature) start 280 below that card. With every event before the expiry, it's at the bottom. An update re-adds it rather than moving it, so it stays drawn above the center line.

## How an update finds things

The script lays out the first `board.events` events again to know where everything is, and reads only what it updates: `--read` asks for the banners, the expiry marker, the subtitle, the title, the table and any blocker that's been resolved. With a full `fetch` instead (a board drawn before `board.events` existed), it counts the cards. Either way it recognizes each part by type, size and text: cards are 420 x 120 rects, banners 1040 x 50 rects starting "Phase N · ", the expiry marker the 240-wide pill saying "Contract expiry", the center line the 6-wide rect, the subtitle the text with "Contract expiry", the title the text in a title font (l3, l2 or l1), and the board's table. Resizing these by hand stops the script from finding them.
