# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11,<13"]
# ///
"""Offline helper for building lo-fi wireframes with the Whimsical MCP.

It never calls an MCP server or the network. The agent calls Whimsical and passes
results in; this script keeps the run ledger, checks drafts before they're sent,
and draws measuring grids.

  uv run scripts/wireframes.py <command> --help
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

MAX_SCREENS = 15
MAX_ELEMENTS = 200
MAX_DEPTH = 10
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# An iphone-14 frame is 432x892; its content area is 392x792, 80 px below the frame's top.
FRAME_W, FRAME_H = 432, 892
CONTENT_W = 392
LINE_H = {"xs": 16, "s": 20, "m": 24, "l0": 28, "l1": 36, "l2": 48, "l3": 72}
TEXT_SIZES = ["xs", "s", "m", "l0", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8"]
COLORS = {"white", "light-gray", "silver", "default", "blue", "whimsy-blue", "dark-purple", "purple",
          "green", "dark-green", "brown", "pale-red", "red", "orange", "yellow"}

# Board layout: five frames per row, with room right of each frame for its source screenshot
# (852 px tall, 132 px right of the frame, 4 px below its top) and a credit link under it.
COLUMN_PITCH = 1439
ROW_PITCH = 1376
COLUMNS = 5
SHOT_GAP = 132
SHOT_TOP = 4
SHOT_H = 852
LINK_GAP = 20
LINK_TEXT = "See screen on Mobbin.com"

CONTAINER_STYLE = {"flex-direction", "gap", "padding", "align-items", "justify-content", "flex-wrap",
                   "width", "height", "flex", "flex-grow", "flex-shrink", "margin"}
ELEMENT_STYLE = {"width", "height", "flex", "flex-grow", "flex-shrink", "align-self", "margin"}
DIRECTIONS = {"row", "column", "row-reverse", "column-reverse"}
ALIGNS = {"center", "flex-end", "flex-start", "stretch"}
JUSTIFIES = {"center", "flex-end", "flex-start", "space-around", "space-between", "space-evenly"}
NUMERIC_STYLE = {"gap", "width", "height", "flex", "flex-grow", "flex-shrink"}

# Props each wireframe element accepts. The MCP refuses any other prop.
_TEXT_PROPS = {"text", "label", "color", "size", "font-size"}
PROPS = {
    "w-button": _TEXT_PROPS | {"deco", "text-align", "state", "icon-name", "icon-placement"},
    "w-link": _TEXT_PROPS | {"deco", "text-align", "state", "icon-name", "icon-placement"},
    "w-tag": _TEXT_PROPS | {"deco", "text-align", "icon-name", "icon-placement"},
    "w-input": _TEXT_PROPS | {"state", "icon-name", "icon-placement", "filled"},
    "w-textarea": _TEXT_PROPS | {"state", "icon-name", "icon-placement", "filled"},
    "w-dropdown": _TEXT_PROPS | {"items", "state", "filled"},
    "w-checkbox": _TEXT_PROPS | {"items", "state"},
    "w-radio-button": _TEXT_PROPS | {"items", "state"},
    "w-h-tabs": _TEXT_PROPS | {"items", "icon-placement"},
    "w-v-tabs": _TEXT_PROPS | {"items", "icon-placement"},
    "w-tooltip": _TEXT_PROPS | {"arrow-placement"},
    "w-annotation": _TEXT_PROPS | {"deco"},
    "w-slider": {"label", "color", "size", "font-size", "pos"},
    "w-progress-bar": {"label", "color", "size", "font-size", "pos"},
    "w-stars": {"label", "color", "size", "font-size", "pos"},
    "w-toggle": {"color", "size", "font-size", "state"},
    "w-shape": {"color", "deco", "shape-type", "icon-name"},
    "w-divider": {"color", "deco"},
    "w-overlay": {"color"},
    "w-pattern": {"color"},
    "w-lorem": {"color", "size", "font-size", "text-align"},
    "w-block-font": {"color", "size", "font-size", "text-align"},
    "w-icon": {"color", "icon-name"},
    "shape": {"text", "shape-type", "color", "deco"},
    "text": {"text", "color", "font-size", "text-align"},
    "link": {"text", "url"},
    "icon": {"icon-name", "deco", "color"},
}
TABS = {"w-h-tabs", "w-v-tabs"}
TAB_ITEM_KEYS = {"text", "icon-name", "selected"}

# Icon names known to draw the expected glyph as an outline icon.
VERIFIED_ICONS = {
    "zoom-2": "search magnifier", "favorite": "heart", "single-01": "person", "single-02": "person (alt)",
    "basket": "shopping basket", "shopping-cart": "cart (filled look)", "house": "home",
    "home-2": "home with person", "cutlery": "fork and knife", "apple-2": "apple", "bag-16": "shopping bag",
    "table": "table", "arrow-right": "arrow right", "ctrl-down": "chevron down", "ctrl-right": "chevron right",
    "ctrl-left": "chevron left (back)", "e-add": "plus", "e-delete": "minus", "small-add": "small plus",
    "small-delete": "small minus", "bold-add": "heavy plus (filled)", "tag": "price tag",
    "grid-interface": "2x2 grid", "gallery-view": "4-pane grid", "apps": "four circles", "box": "archive box",
    "chat": "speech bubble", "comment": "round speech bubble", "chat-33": "two speech bubbles",
    "phone-2": "phone handset", "car-2": "car", "menu-8": "hamburger menu", "shield": "shield with star",
    "upload": "share (tray with up arrow)", "share-2": "share nodes", "upload-2": "upload box",
    "image": "picture placeholder", "security": "split shield", "lock": "padlock",
    "calendar": "calendar", "globe": "globe", "briefcase-24": "briefcase", "circle-08": "person in circle",
    "clock": "clock", "time-clock": "clock with arrow",
    "launch": "external link (box with arrow out)", "refund": "refund (coin with return arrow)",
    "alert-circle-i": "info circle", "alert-circle-exc": "alert / report circle with exclamation",
    "e-remove": "close X", "preferences": "filter sliders", "copy-2": "copy (two squares)",
    "cart-simple-add": "add to cart", "dots": "more (three horizontal dots)", "arrow-down": "arrow down",
    "verified": "verified badge with check", "bell-55": "notification bell", "box-2": "package box (orders)",
}
# Names that draw a different icon than the word suggests, with what to use instead. The MCP maps
# plus, minus, close, x, search, heart, home, user, chevron-*, hamburger and bell to the usual glyph.
BAD_ICONS = {"phone": "phone-2", "shield-check": "shield",
             "share": "upload (iOS share; `share` draws a box with a curved arrow)",
             "star": "a ★ text glyph (the star icon draws a star in a box)"}

MARKER = re.compile(r"\*\*|~~")


# ---------------------------------------------------------------- ledger

def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def load(run):
    path = Path(run) / "run.json"
    if not path.exists():
        sys.exit(f"No run ledger at {path}. Run `init` first.")
    return json.loads(path.read_text())


def save(run, state):
    path = Path(run) / "run.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def screen_of(state, key):
    for screen in state["screens"]:
        if screen["key"] == key or screen["file"] == key:
            return screen
    sys.exit(f"Unknown screen {key!r}. Keys: {', '.join(s['key'] for s in state['screens'])}")


def frame_center(index):
    col, row = index % COLUMNS, index // COLUMNS
    return {"x": col * COLUMN_PITCH + FRAME_W // 2, "y": row * ROW_PITCH + FRAME_H // 2}


def cmd_init(args):
    run = Path(args.run)
    source = Path(args.screenshots) if args.screenshots else run / "screenshots"
    if (run / "run.json").exists():
        sys.exit(f"{run} already has a run ledger. Resume it, or choose another folder.")
    if not source.is_dir():
        sys.exit(f"No screenshot folder at {source}.")
    images = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not 1 <= len(images) <= MAX_SCREENS:
        sys.exit(f"Found {len(images)} screenshots in {source}; need 1 to {MAX_SCREENS}.")
    manifest = source / "selection.json"
    meta = {}
    app = args.app or run.name
    if manifest.exists():
        selection = json.loads(manifest.read_text())
        app = args.app or selection.get("app_name") or app
        meta = {s["file"]: s for s in selection.get("screens", [])}
    screens = []
    for i, image_path in enumerate(images):
        with Image.open(image_path) as image:
            width, height = image.size
        info = meta.get(image_path.name, {})
        label = info.get("label") or re.sub(r"^\d+\s*-\s*|\s*-\s*[0-9a-f]{8}$", "", image_path.stem).strip()
        key = f"{i + 1:02d}"
        screens.append({
            "key": key, "file": image_path.name, "label": label, "title": f"{key} {label}",
            "mobbin_url": info.get("mobbin_url"), "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "width": width, "height": height, "status": "pending", "frame_id": None,
            "renders": 0, "reviews": 0, "findings": [], "link_id": None, "notes": "",
        })
    run.mkdir(parents=True, exist_ok=True)
    (run / "drafts").mkdir(exist_ok=True)
    state = {"app": app, "source": str(source), "created": now(), "board_id": None, "board_url": None,
             "accent": None, "icons_checked": [], "screens": screens}
    save(run, state)
    print(json.dumps({"run": str(run), "app": app, "screens": [(s["key"], s["label"], s["mobbin_url"])
                                                              for s in screens]}, indent=1, ensure_ascii=False))


def cmd_board(args):
    state = load(args.run)
    if state["board_id"] and state["board_id"] != args.id:
        sys.exit(f"This run already owns board {state['board_id']}; refusing to switch to {args.id}.")
    state.update(board_id=args.id, board_url=args.url or state.get("board_url"))
    if args.accent:
        state["accent"] = args.accent
    if args.swatch_board:
        if args.swatch_board == state["board_id"]:
            sys.exit("The icon check must live on a separate scratch board, never on the wireframe board.")
        state["swatch_board_id"] = args.swatch_board
    save(args.run, state)
    print(json.dumps({k: state.get(k) for k in ("app", "board_id", "board_url", "accent", "swatch_board_id")}))


def cmd_set(args):
    state = load(args.run)
    screen = screen_of(state, args.screen)
    for pair in args.pairs:
        key, _, value = pair.partition("=")
        if key not in screen:
            sys.exit(f"Unknown field {key!r}.")
        if key == "frame_id" and screen["frame_id"] and value != screen["frame_id"]:
            sys.exit(f"Screen {screen['key']} already has frame {screen['frame_id']}; never create a second one.")
        try:
            screen[key] = json.loads(value)
        except json.JSONDecodeError:
            screen[key] = value
    for field in args.bump or []:
        screen[field] = int(screen.get(field) or 0) + 1
    screen["updated"] = now()
    save(args.run, state)
    print(json.dumps(screen, ensure_ascii=False))


def cmd_icons(args):
    state = load(args.run)
    known = set(icon_index().get("names", []))
    bad = [n for n in args.names if n in BAD_ICONS or (known and n not in known)]
    if bad:
        sys.exit(f"Not recording names that are misleading or not in the icon set: {', '.join(bad)}")
    state["icons_checked"] = sorted(set(state.get("icons_checked", [])) | set(args.names))
    save(args.run, state)
    print(json.dumps(state["icons_checked"]))


def cmd_status(args):
    state = load(args.run)
    print(f"{state['app']}  board: {state.get('board_url') or state.get('board_id')}  accent: {state.get('accent')}"
          f"  icon check board: {state.get('swatch_board_id') or '-'}")
    counts = {}
    for s in state["screens"]:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
        open_findings = [f for f in s["findings"] if f.get("severity") == "major"]
        print(f"  {s['key']} {s['label'][:28]:28} {s['status']:12} renders={s['renders']} reviews={s['reviews']}"
              f" link={'y' if s['link_id'] else 'n'}"
              f" frame={s['frame_id'] or '-'} major={len(open_findings)}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


# ---------------------------------------------------------------- draft checks

class Lint:
    def __init__(self, checked_icons=()):
        self.checked_icons = set(checked_icons)
        self.errors, self.warnings = [], []
        self.leaves = []
        self.groups = {}

    def error(self, path, message):
        self.errors.append(f"{path}: {message}")

    def warn(self, path, message):
        self.warnings.append(f"{path}: {message}")


def strip_markdown(text):
    text = re.sub(r"\*\*|~~|`|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", text or "")
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def check_markdown(lint, path, text):
    if len(MARKER.findall(text)) % 2:
        lint.warn(path, f"unbalanced ** or ~~ in {text!r}")


def is_hiccup(value):
    return isinstance(value, list) and value and isinstance(value[0], str)


def check_style(lint, path, style, allowed, is_container):
    if not isinstance(style, dict):
        lint.error(path, "layout/style must be an object")
        return {}
    for key, value in style.items():
        if key not in allowed:
            hint = " Containers can't take margin: pad the parent or put margin on a leaf." if key == "margin" else ""
            lint.error(path, f"layout/style {key!r} not allowed on {'div' if is_container else 'element'}.{hint}")
        elif key == "flex-direction" and value not in DIRECTIONS:
            lint.error(path, f"bad flex-direction {value!r}")
        elif key in ("align-items", "align-self") and value not in ALIGNS:
            lint.error(path, f"bad {key} {value!r}")
        elif key == "justify-content" and value not in JUSTIFIES:
            lint.error(path, f"bad justify-content {value!r}")
        elif key in ("padding", "margin"):
            sides = value.values() if isinstance(value, dict) else [value]
            if isinstance(value, dict) and set(value) - {"top", "right", "bottom", "left"}:
                lint.error(path, f"{key} keys must be top/right/bottom/left")
            if not all(isinstance(v, (int, float)) for v in sides):
                lint.error(path, f"{key} values must be numbers")
        elif key in NUMERIC_STYLE and not isinstance(value, (int, float)):
            lint.error(path, f"{key} must be a number, not {value!r}")
    return style


def walk(lint, node, path, depth, parent, group):
    """`parent` is the parent div's style; `group` is the path of the enclosing `group: true` div."""
    if depth > MAX_DEPTH:
        lint.error(path, f"nesting deeper than {MAX_DEPTH}")
        return
    if not is_hiccup(node):
        lint.error(path, "expected a hiccup array [tag, {attrs}, ...children]")
        return
    tag = node[0]
    has_attrs = len(node) > 1 and isinstance(node[1], dict)
    attrs = node[1] if has_attrs else {}
    children = node[2:] if has_attrs else node[1:]
    if tag == "div":
        for key in attrs:
            if key == "wf/group":
                lint.error(path, 'wf/group is gone: put "group": true on the div; the MCP groups it as it renders')
            elif key not in ("layout/style", "group"):
                lint.error(path, f"div only takes layout/style and group, not {key!r}")
        style = check_style(lint, path, attrs.get("layout/style", {}), CONTAINER_STYLE, True)
        if path == "$" and any(k.startswith("margin") for k in style):
            lint.error(path, "the root div can't take margin: it has no parent")
        direction = style.get("flex-direction")
        if direction is None:
            lint.error(path, "set flex-direction explicitly on every div")
            direction = "column"
        if "group" in attrs:
            if not isinstance(attrs["group"], bool):
                lint.error(path, "group must be true or false")
            elif attrs["group"]:
                if group is not None:
                    lint.groups[group].append(path)
                lint.groups[path] = []
                group = path
        for i, child in enumerate(children):
            walk(lint, child, f"{path}/{i}", depth + 1, {"flex-direction": direction, **style}, group)
        return
    if tag not in PROPS:
        lint.error(path, f"unknown tag {tag!r} (there's no w-image, w-map or w-avatar; see techniques.md)")
        return
    if children:
        lint.error(path, f"{tag} can't have children; layer it with a negative margin instead")
    allowed = PROPS[tag] | {"layout/style"}
    for key in attrs:
        if key == "wf/color":
            lint.error(path, "wf/color is gone: give the icon color directly")
        elif key not in allowed:
            lint.error(path, f"{tag} doesn't take {key!r} (takes {', '.join(sorted(PROPS[tag]))})")
    style = check_style(lint, path, attrs.get("layout/style", {}), ELEMENT_STYLE, False)
    if "size" in attrs and "font-size" in attrs:
        lint.error(path, "set size or font-size, not both")
    if "color" in attrs and attrs["color"] not in COLORS and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(attrs["color"])):
        lint.error(path, f"color {attrs['color']!r} isn't a palette color")
    text = attrs.get("text")
    if isinstance(text, str):
        check_markdown(lint, path, text)
    if tag == "text":
        size = attrs.get("font-size", "m")
        if size not in TEXT_SIZES:
            lint.error(path, f"bad font-size {size!r}")
        if "height" in style:
            lint.warn(path, "leave text height out: the MCP measures text, and an explicit height must match exactly")
    if tag == "icon":
        if attrs.get("deco") not in ("outline", "fill", "multicolor"):
            lint.error(path, "icon needs deco: outline (or fill)")
        if "color" in attrs and attrs.get("deco") == "multicolor":
            lint.error(path, "a multicolor icon can't take color")
        if "width" not in style or "height" not in style:
            lint.error(path, "icon needs layout/style width and height (default is 96px)")
    if tag == "w-icon":
        lint.warn(path, "w-icon draws a filled glyph; use `icon` with deco outline unless filled is intended")
    if tag in ("w-icon", "w-shape", "icon", "w-button", "w-tag", "w-input", "w-textarea") and "icon-name" in attrs:
        check_icon(lint, path, attrs["icon-name"])
    if "items" in attrs:
        check_items(lint, path, tag, attrs["items"])
    pos = attrs.get("pos")
    if tag in ("w-stars", "w-progress-bar", "w-slider") and pos is not None and (
            not isinstance(pos, (int, float)) or not 0 <= pos <= 1):
        lint.error(path, "pos must be between 0 and 1 (stars round to whole stars: stars / 5)")
    if tag == "w-toggle" and "state" not in attrs:
        lint.error(path, "set w-toggle state (selected or unselected); the default looks on")
    if tag == "w-shape" and attrs.get("icon-name") == "image" and attrs.get("deco") != "fill":
        lint.warn(path, "image placeholder with a border looks heavy: use deco fill (light-gray on white, "
                        "white on light-gray surfaces)")
    if (tag == "w-shape" and attrs.get("deco") == "outline" and attrs.get("shape-type", "rect") == "rect"
            and style.get("height", 0) >= 60 and style.get("width", 999) >= 200):
        lint.warn(path, "outlined card: surfaces are filled (light-gray), outlines are for fields and controls")
    if tag == "w-shape" and attrs.get("deco") == "outline" and attrs.get("shape-type") in ("ellipse", "pill"):
        lint.warn(path, "outlined circle/pill: default to a borderless fill (light-gray on white, white on "
                        "light-gray) unless the source border matters or it floats over white")
    if tag == "w-button" and attrs.get("color") == "light-gray" and attrs.get("deco") == "fill" \
            and attrs.get("state") != "disabled":
        lint.warn(path, "a light-gray w-button renders as a darker blue-gray: use a w-tag or a layered pill shape")
    if tag == "w-shape" and attrs.get("shape-type", "rect") not in ("rect", "ellipse", "pill"):
        lint.error(path, "shape-type must be rect, ellipse or pill")
    leaf = {"index": len(lint.leaves), "tag": tag, "path": path, "group": group}
    if isinstance(text, str):
        leaf["text"] = strip_markdown(text)
    lint.leaves.append(leaf)
    if group is not None:
        lint.groups[group].append(leaf["index"])


def check_items(lint, path, tag, items):
    if not isinstance(items, list):
        lint.error(path, "items must be a list")
        return
    for i, item in enumerate(items):
        if isinstance(item, str):
            continue
        if tag not in TABS or not isinstance(item, dict):
            extra = " or {text, icon-name, selected}" if tag in TABS else ""
            lint.error(path, f"items[{i}] must be a string{extra}")
        elif set(item) - TAB_ITEM_KEYS or not isinstance(item.get("text"), str):
            lint.error(path, f"items[{i}] takes text (required), icon-name and selected")
        elif "icon-name" in item:
            check_icon(lint, f"{path}/items[{i}]", item["icon-name"])


def check_icon(lint, path, name):
    index = icon_index()
    known = set(index.get("names", []))
    if name in BAD_ICONS:
        lint.error(path, f"icon-name {name!r} draws something else; use {BAD_ICONS[name]}")
    elif known and name not in known:
        target = index.get("aliases", {}).get(name)
        if target:
            lint.warn(path, f"icon-name {name!r} is an alias of {target!r}; use the real name")
        else:
            lint.error(path, f"icon-name {name!r} isn't in the icon set: the MCP refuses it or swaps in a close "
                             "match. Find a real name with `wireframes.py icon <concept>`")
    elif (name not in VERIFIED_ICONS and name not in lint.checked_icons
          and name not in index.get("descriptions", {})):
        lint.warn(path, f"icon-name {name!r} exists but has no description; check it in a swatch first")


def lint_layout(layout, checked_icons=()):
    lint = Lint(checked_icons)
    if not is_hiccup(layout) or layout[0] != "div":
        lint.error("$", 'root must be ["div", {...}, ...]')
        return lint
    walk(lint, layout, "$", 0, {"flex-direction": "column"}, None)
    if len(lint.leaves) > MAX_ELEMENTS:
        lint.error("$", f"{len(lint.leaves)} elements; a wireframe takes at most {MAX_ELEMENTS}")
    elif len(lint.leaves) > MAX_ELEMENTS - 20:
        lint.warn("$", f"{len(lint.leaves)} elements, close to the {MAX_ELEMENTS} limit")
    for group_path, members in lint.groups.items():
        if len(members) < 2:
            lint.error(group_path, f"a group needs at least 2 elements; this one holds {len(members)}")
    return lint


def report(lint):
    for message in lint.errors:
        print(f"ERROR   {message}", file=sys.stderr)
    for message in lint.warnings:
        print(f"warning {message}", file=sys.stderr)


def cmd_check(args):
    lint = lint_layout(json.loads(Path(args.draft).read_text()))
    report(lint)
    print(json.dumps({"errors": len(lint.errors), "warnings": len(lint.warnings), "elements": len(lint.leaves),
                      "groups": {k: len(v) for k, v in lint.groups.items()}}))
    sys.exit(1 if lint.errors else 0)


def cmd_prepare(args):
    state = load(args.run)
    screen = screen_of(state, args.screen)
    if not state.get("board_id"):
        sys.exit("Record the board first: `wireframes.py board <run> --id <board id>`.")
    drafts = Path(args.run) / "drafts"
    draft = drafts / f"{screen['key']}.json"
    if not draft.exists():
        sys.exit(f"Write the draft to {draft} first.")
    layout = json.loads(draft.read_text())
    lint = lint_layout(layout, state.get("icons_checked", []))
    report(lint)
    if lint.errors:
        sys.exit(f"{len(lint.errors)} error(s); fix the draft before rendering.")
    # Create the frame once; every later render replaces its contents in place.
    if screen["frame_id"]:
        tool = "wireframe_edit"
        arguments = {"board_id": state["board_id"], "target_id": screen["frame_id"], "frame_type": "iphone-14",
                     "layout": layout}
    else:
        tool = "add_board_content"
        center = frame_center(state["screens"].index(screen))
        arguments = {"type": "wireframe", "board_id": state["board_id"], "title": screen["title"],
                     "x": center["x"], "y": center["y"], "data": {"frame_type": "iphone-14", "layout": layout}}
    call = {"tool": tool, "arguments": arguments}
    (drafts / f"{screen['key']}.render.json").write_text(json.dumps(call, ensure_ascii=False) + "\n")
    print(json.dumps(call, ensure_ascii=False, separators=(",", ":")))


# ---------------------------------------------------------------- listings from fetch

def listing_rows(raw):
    """Rows from a saved `fetch` result: the JSON envelope or just its CSV text."""
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            text = data["text"]
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("type,id,parentId"))
    except StopIteration:
        sys.exit("No `type,id,parentId,...` header found in the listing.")
    columns = lines[start].split(",")
    rows = []
    for line in lines[start + 1:]:
        if not line.strip() or line.startswith("Palette:"):
            break
        parts = line.split(",", len(columns) - 1)
        parts += [""] * (len(columns) - len(parts))
        row = dict(zip(columns, parts))
        row["kind"] = row["type"].split(":")[0]
        row["raw_text"] = row.get("text", "")
        row["text"] = re.sub(r"( \[(props|url): .*?\])+$", "", row.get("text", ""))
        rows.append(row)
    return rows


def cmd_links(args):
    state = load(args.run)
    frames = {r["id"]: r for r in listing_rows(Path(args.listing).read_text()) if r["kind"] == "frame"}
    operations, missing = [], []
    for screen in state["screens"]:
        if screen["link_id"] or not screen["mobbin_url"]:
            continue
        frame = frames.get(screen["frame_id"] or "")
        if not frame or "x" not in frame:
            missing.append(screen["key"])
            continue
        x, y, h = float(frame["x"]), float(frame["y"]), float(frame["height"])
        # Under the frame for now; arranging moves it under the screenshot once one is placed.
        operations.append({"op": "add", "type": "link", "url": screen["mobbin_url"], "text": LINK_TEXT,
                           "x": x, "y": y + h + LINK_GAP, "temp_id": f"link{screen['key']}"})
    if missing:
        print(f"warning: no frame position for screens {', '.join(missing)}; fetch frames with detail "
              "'detailed'", file=sys.stderr)
    result = {"id": state["board_id"], "operations": operations}
    compact = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    (Path(args.run) / "links.edit.json").write_text(compact + "\n")
    print(compact)


# ---------------------------------------------------------------- icons

_ICON_INDEX = None


def icon_index():
    global _ICON_INDEX
    if _ICON_INDEX is None:
        path = Path(__file__).with_name("icon_index.json")
        _ICON_INDEX = json.loads(path.read_text()) if path.exists() else {"concepts": {}, "descriptions": {}}
    return _ICON_INDEX


def search_icons(query, limit=8):
    """Concept-first icon search: aliases and states first, then visual descriptions and verified names."""
    index = icon_index()
    descriptions = index["descriptions"]
    words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if w]
    scores = {}

    def add(name, points, concept=None):
        entry = scores.setdefault(name, {"name": name, "score": 0, "concepts": set()})
        entry["score"] += points
        if concept:
            entry["concepts"].add(concept)

    for concept, data in index["concepts"].items():
        terms = [concept, *data.get("aliases", [])]
        exact = query.lower().strip() in terms
        hits = sum(any(w == t or w in t.split() for t in terms) for w in words)
        if exact or hits:
            add(data["icon-name"], 10 if exact else 5 * hits, concept)
            for label, name in {**data.get("states", {}), **data.get("variants", {})}.items():
                add(name, 6 if exact else 3 * hits, f"{concept} ({label})")
    for name, text in descriptions.items():
        hits = sum(w in text.lower() for w in words) + 2 * sum(w in name for w in words)
        if hits:
            add(name, hits)
    for name, text in VERIFIED_ICONS.items():
        hits = sum(w in text or w in name for w in words)
        if hits:
            add(name, 12 * hits)
    vendor = re.compile(r"^(aws|amazon|azure|gcp|google-cloud)-")
    if not any(vendor.match(w + "-") for w in words):
        scores = {n: e for n, e in scores.items() if not vendor.match(n)}
    results = []
    for entry in sorted(scores.values(), key=lambda e: -e["score"])[:limit]:
        name = entry["name"]
        results.append({"name": name, "concepts": sorted(entry["concepts"]),
                        "looks_like": descriptions.get(name) or VERIFIED_ICONS.get(name, ""),
                        "checked_outline": name in VERIFIED_ICONS,
                        "avoid": BAD_ICONS.get(name)})
    return results


def cmd_icon(args):
    for query in args.queries:
        print(json.dumps({"query": query, "results": search_icons(query, args.limit)}, ensure_ascii=False))


def cmd_swatch(args):
    if len(args.names) > 50:
        sys.exit("At most 50 icons per swatch.")
    rows = []
    for i in range(0, len(args.names), 5):
        cells = [["div", {"layout/style": {"flex-direction": "column", "align-items": "center", "gap": 2, "width": 72}},
                  ["icon", {"icon-name": name, "deco": "outline", "layout/style": {"width": 24, "height": 24}}],
                  ["text", {"text": name, "font-size": "xs", "text-align": "center", "layout/style": {"width": 72}}]]
                 for name in args.names[i:i + 5]]
        rows.append(["div", {"layout/style": {"flex-direction": "row", "gap": 4}}, *cells])
    print(json.dumps(["div", {"layout/style": {"flex-direction": "column", "gap": 8, "padding": 8}}, *rows],
                     separators=(",", ":")))


# ---------------------------------------------------------------- measuring grid

GRID_SCALE = 2
GRID_HALVES = (("top", -54, 380), ("bot", 370, 800))


def grid_image(source, y0, y1):
    """The screenshot at frame scale (x2) with a grid labelled in frame px; y starts at -54 (the status bar)."""
    from PIL import ImageDraw, ImageFont

    with Image.open(source) as raw:
        image = raw.convert("RGB")
    s = GRID_SCALE
    image = image.resize((CONTENT_W * s, round(image.height * CONTENT_W * s / image.width)), Image.LANCZOS)
    crop = image.crop((0, (y0 + 54) * s, CONTENT_W * s, min(image.height, (y1 + 54) * s)))
    pad = 60
    canvas = Image.new("RGB", (crop.width + pad, crop.height), "white")
    canvas.paste(crop, (pad, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    for fy in range((y0 // 10) * 10, y1 + 1, 10):
        py = (fy - y0) * s
        if 0 <= py < canvas.height:
            major = fy % 50 == 0
            draw.line([(0 if major else pad, py), (canvas.width, py)], fill=(255, 0, 0) if major else (255, 170, 170))
            if major:
                draw.text((2, py + 1), str(fy), fill=(200, 0, 0), font=font)
    for fx in range(0, CONTENT_W + 1, 10):
        px = pad + fx * s
        major = fx % 50 == 0
        draw.line([(px, 0), (px, canvas.height)], fill=(0, 0, 255) if major else (180, 180, 255))
        if major:
            draw.text((px + 2, 2), str(fx), fill=(0, 0, 200), font=font)
    return canvas


def cmd_grid(args):
    state = load(args.run)
    screen = screen_of(state, args.screen)
    out_dir = Path(args.run) / "grid"
    out_dir.mkdir(exist_ok=True)
    written = []
    for name, y0, y1 in GRID_HALVES:
        out = out_dir / f"{screen['key']}-{name}.png"
        grid_image(Path(state["source"]) / screen["file"], y0, y1).save(out)
        written.append(str(out))
    print(json.dumps({"key": screen["key"], "grids": written}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="create a run ledger for a folder of screenshots")
    p.add_argument("run", help="run folder, e.g. wireframes/Airbnb")
    p.add_argument("--screenshots", help="screenshot folder (default: <run>/screenshots)")
    p.add_argument("--app", help="app name (default: from selection.json or the folder name)")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("board", help="record the board this run owns")
    p.add_argument("run")
    p.add_argument("--id", required=True)
    p.add_argument("--url")
    p.add_argument("--accent")
    p.add_argument("--swatch-board", help="ID of the scratch board holding the icon check (deleted at the end)")
    p.set_defaults(func=cmd_board)
    p = sub.add_parser("set", help="update a screen's ledger fields: key=value (JSON values allowed)")
    p.add_argument("run")
    p.add_argument("screen")
    p.add_argument("pairs", nargs="*")
    p.add_argument("--bump", action="append", choices=["renders", "reviews"])
    p.set_defaults(func=cmd_set)
    p = sub.add_parser("status", help="per-screen progress")
    p.add_argument("run")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("grid", help="screenshot with a frame-coordinate grid, for measuring")
    p.add_argument("run")
    p.add_argument("screen")
    p.set_defaults(func=cmd_grid)
    p = sub.add_parser("check", help="check a draft file")
    p.add_argument("draft")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("prepare", help="check drafts/<key>.json and print the MCP call that renders it")
    p.add_argument("run")
    p.add_argument("screen")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("links", help="credit-link edit from a saved listing of the board's frames")
    p.add_argument("run")
    p.add_argument("listing")
    p.set_defaults(func=cmd_links)
    p = sub.add_parser("icon", help="find icon names by meaning, with visual descriptions")
    p.add_argument("queries", nargs="+", help="one concept per argument, e.g. 'share' 'notification bell'")
    p.add_argument("--limit", type=int, default=6)
    p.set_defaults(func=cmd_icon)
    p = sub.add_parser("icons", help="record icon names you checked by eye in a swatch")
    p.add_argument("run")
    p.add_argument("names", nargs="+")
    p.set_defaults(func=cmd_icons)
    p = sub.add_parser("swatch", help="layout of a labelled icon swatch, to check icons by eye")
    p.add_argument("names", nargs="+")
    p.set_defaults(func=cmd_swatch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
