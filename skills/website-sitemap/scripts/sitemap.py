#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Read a website's sitemaps and turn its pages into a Whimsical mind map or flowchart.

  python3 sitemap.py fetch <site>
      Find the site's sitemap (robots.txt, then /sitemap.xml and /sitemap_index.xml), read it and
      every sitemap nested in it, and save the pages in sitemaps/<site>/pages.txt. Prints how many
      pages, language versions and sections it found. Exits with 3 when the site has no sitemap.
  python3 sitemap.py draw sitemaps/<site> --type mindmap|flowchart|both [--locale CODE] [--limit N]
                         [--per-level N] [--section PATH]
      Build the tree of pages, show at most 30 children under any node (the rest become "and N other
      pages"), then fold the longest lists of pages until it has at most 1000 nodes, and write
      mindmap.md or flowchart.mmd: the text to hand to the Whimsical MCP as is.
      Names come from the URLs; labels.json in the same folder renames a path ("/hr": "HR Team") or
      fixes a word in every name ("acmepay": "AcmePay").
      --section draws one section on its own, like /blog. --icon puts an icon from Whimsical's set on
      the root, like logo-github.
  python3 sitemap.py note sitemaps/<site>
      Print the text to put above the drawing: the sitemap it read, and how much of it is shown.

Network: only the site named, its subdomains, and the sitemap files on them. The script never
calls Whimsical.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import heapq
import io
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree

USER_AGENT = "WhimsicalSitemapSkill/1.0 (+https://github.com/WhimsicalCode/skills)"
TIMEOUT = 30
MAX_REDIRECTS = 5
MAX_DOWNLOAD = 50 * 1024 * 1024    # the sitemap protocol caps a file at 50 MB uncompressed
MAX_UNZIPPED = 100 * 1024 * 1024
MAX_FILES = 2000
MAX_PAGES = 2_000_000
WORKERS = 8
DEFAULT_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
NOT_FOUND = 3                      # exit status when the site has no sitemap

DEFAULT_LIMIT = 1000
MAX_LIMIT = 2000                   # the most nodes the Whimsical MCP takes in one mind map
MAX_FLOWCHART = 1000               # the most nodes it takes in one flowchart
COLLAPSE_OVER = 8                  # a mind map node listing more pages than this starts collapsed
MAX_TEXT = 102_400                 # the most characters the Whimsical MCP takes in one string
MAX_ROWS = 200                     # the most rows the Whimsical MCP takes in one flowchart table
PER_LEVEL = 30                     # the most children a node shows; the rest become "and N other pages"
# Collections: siblings made from one pattern (companies, numbered pages, dated posts) are grouped in one node.
COLLECTION_MIN = 8                 # siblings with one shape before they count as a collection
NUMBERED_MIN = 3                   # the same for plain numbers: a number is almost never a main page
TEMPLATE_SHARE = 0.6               # siblings sharing a child page (all have /candidates) come from a template
LIST_SHARE = 0.5                   # a level whose single pages are mostly generated is a list (a blog)
GENERATED = {"N", "YEAR", "ID", "DOMAIN", "w4+"}
PLAIN = {"w1", "w2"}               # one to three plain words: what main pages look like (about, contact-sales)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
DOMAIN_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*\.[a-z]{2,10}", re.I)
FILE_TYPES = {"pdf", "vcf", "xml", "json", "txt", "csv", "zip", "png", "jpg", "jpeg", "gif", "svg", "mp4"}
MAX_LABEL = 60

# A language prefix: `de`, `en-us`, `pt_BR`, `zh-hans`. A two-letter section like /it/ or /id/ only
# counts as one when the site has several (see language_prefixes).
LOCALE = re.compile(r"^([a-z]{2})(?:[-_](?:[a-z]{2}|[0-9]{3}|[a-z]{4}))?$", re.I)
ISO_639_1 = {
    "aa", "ab", "ae", "af", "ak", "am", "an", "ar", "as", "av", "ay", "az", "ba", "be", "bg", "bh", "bi", "bm",
    "bn", "bo", "br", "bs", "ca", "ce", "ch", "co", "cr", "cs", "cu", "cv", "cy", "da", "de", "dv", "dz", "ee",
    "el", "en", "eo", "es", "et", "eu", "fa", "ff", "fi", "fj", "fo", "fr", "fy", "ga", "gd", "gl", "gn", "gu",
    "gv", "ha", "he", "hi", "ho", "hr", "ht", "hu", "hy", "hz", "ia", "id", "ie", "ig", "ii", "ik", "io", "is",
    "it", "iu", "ja", "jv", "ka", "kg", "ki", "kj", "kk", "kl", "km", "kn", "ko", "kr", "ks", "ku", "kv", "kw",
    "ky", "la", "lb", "lg", "li", "ln", "lo", "lt", "lu", "lv", "mg", "mh", "mi", "mk", "ml", "mn", "mr", "ms",
    "mt", "my", "na", "nb", "nd", "ne", "ng", "nl", "nn", "no", "nr", "nv", "ny", "oc", "oj", "om", "or", "os",
    "pa", "pi", "pl", "ps", "pt", "qu", "rm", "rn", "ro", "ru", "rw", "sa", "sc", "sd", "se", "sg", "si", "sk",
    "sl", "sm", "sn", "so", "sq", "sr", "ss", "st", "su", "sv", "sw", "ta", "te", "tg", "th", "ti", "tk", "tl",
    "tn", "to", "tr", "ts", "tt", "tw", "ty", "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "wo", "xh", "yi",
    "yo", "za", "zh", "zu",
}
ENGLISH = ("en-us", "en", "en-gb")
PAGE_EXTENSIONS = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp")

SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to",
               "vs", "via", "with"}
ACRONYMS = {w.lower(): w for w in (
    "AI", "API", "APIs", "AR", "AWS", "B2B", "B2C", "CEO", "CRM", "CSS", "CTO", "DevOps", "eBook", "ESG", "EU",
    "FAQ", "FAQs", "GDPR", "GPU", "GPUs", "HPC", "HR", "HTML", "iOS", "iPad", "iPhone", "IoT", "JS", "KPI",
    "KPIs", "LLM", "LLMs", "macOS", "ML", "MCP", "NFT", "OKR", "OKRs", "PDF", "PR", "QA", "RTX", "SaaS", "SDK",
    "SDKs", "SEO", "SLA", "SMS", "SQL", "SSO", "UI", "UK", "URL", "US", "USA", "UX", "VR", "XR",
)}
# What a label may hold: Mermaid reads ( ) as a method, { } as the end of a table, * and $ as styling,
# quotes as the end of a name and %% as a comment; Markdown reads * _ ` as formatting.
UNSAFE = re.compile(r"[^\w &'.,:!?+\-/#@]|_")


class SitemapError(Exception):
    """A problem the agent can act on; the message says what to do."""


class NoSitemap(SitemapError):
    """The site has no sitemap, or one without pages: nothing to draw."""


# ---------------------------------------------------------------- fetch

def site_of(text: str) -> tuple[str, str]:
    """The origin to start from and the site's domain: `ACME.com/en-us` gives https://acme.com and acme.com."""
    text = text.strip()
    parsed = urllib.parse.urlparse(text if "://" in text else "https://" + text)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or "." not in host or parsed.username or parsed.port:
        raise SitemapError(f"not a website address: {text!r}. Pass a domain like acme.com or a URL like "
                           "https://www.acme.com.")
    domain = host[4:] if host.startswith("www.") else host
    return f"{parsed.scheme}://{host}", domain


def on_site(url: str, domain: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (parsed.scheme in ("http", "https") and not parsed.username and not parsed.port
            and (host == domain or host.endswith("." + domain)))


class StayOnSite(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, domain: str):
        self.domain = domain

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not on_site(newurl, self.domain):
            raise SitemapError(f"{req.full_url} redirects off the site, to {newurl}; not following it")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_get(domain: str):
    """A function that downloads one on-site URL and returns its bytes, unzipped."""
    opener = urllib.request.build_opener(StayOnSite(domain))

    def get(url: str) -> bytes:
        if not on_site(url, domain):
            raise SitemapError(f"{url} isn't on {domain}; skipped")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                data = response.read(MAX_DOWNLOAD + 1)
        except urllib.error.HTTPError as error:
            raise SitemapError(f"{url}: HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SitemapError(f"{url}: {getattr(error, 'reason', error)}") from None
        if len(data) > MAX_DOWNLOAD:
            raise SitemapError(f"{url} is over 50 MB; skipped")
        if data[:2] == b"\x1f\x8b":
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_UNZIPPED + 1)
            if len(data) > MAX_UNZIPPED:
                raise SitemapError(f"{url} unzips to over 100 MB; skipped")
        return data
    return get


def parse_sitemap(data: bytes, priorities: dict[str, float] | None = None) -> tuple[str, list[str]] | None:
    """('index', sitemap URLs) or ('pages', page URLs), or None when the file isn't a sitemap. Fills
    `priorities` with each page's <priority>, when it has a valid one."""
    text = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if text[:1] == b"<":
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return None
        kind = {"sitemapindex": "index", "urlset": "pages"}.get(local(root.tag))
        if not kind:
            return None
        # Only each entry's own <loc>: image and video sitemaps nest more <loc>s inside an entry.
        locs = []
        for entry in root:
            if local(entry.tag) not in ("sitemap", "url"):
                continue
            fields = {local(child.tag): (child.text or "").strip() for child in entry}
            if fields.get("loc"):
                locs.append(fields["loc"])
                if priorities is not None and kind == "pages":
                    try:
                        value = float(fields.get("priority", ""))
                    except ValueError:
                        continue
                    if 0 <= value <= 1:
                        priorities[fields["loc"]] = value
        return kind, locs
    lines = [line.strip() for line in text.decode("utf-8", "replace").splitlines() if line.strip()]
    if lines and all(re.match(r"https?://\S+$", line) for line in lines):
        return "pages", lines          # a text sitemap: one URL per line
    return None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def robots_sitemaps(origin: str, get) -> list[str]:
    try:
        text = get(origin + "/robots.txt").decode("utf-8", "replace")
    except SitemapError:
        return []
    return [line.split(":", 1)[1].strip() for line in text.splitlines()
            if line.strip().lower().startswith("sitemap:") and line.split(":", 1)[1].strip()]


def fetch_site(site: str, get=None) -> dict:
    """Find and read every sitemap of a site. Raises SitemapError when it has none."""
    origin, domain = site_of(site)
    get = get or http_get(domain)
    report = {"site": origin, "domain": domain, "fetched": date.today().isoformat(),
              "fetched_at": datetime.now().astimezone().isoformat(timespec="minutes"), "sitemaps": [],
              "pages": [], "priorities": {}, "errors": [], "off_site": []}

    listed = robots_sitemaps(origin, get)
    report["off_site"] += [url for url in listed if not on_site(url, domain)]
    starts = [url for url in listed if on_site(url, domain)]
    level = list(dict.fromkeys(starts)) or []
    first = read_all(level, domain, get, report) if level else False
    if not first:
        for path in DEFAULT_PATHS:
            if read_all([origin + path], domain, get, report):
                first = True
                break
    if not first:
        checked = ", ".join(["robots.txt", *DEFAULT_PATHS] + (["the sitemaps robots.txt lists"] if starts else []))
        raise NoSitemap(f"No sitemap found on {domain}: checked {checked}.")
    if not report["pages"]:
        raise NoSitemap(f"{domain} has a sitemap, but it lists no pages on {domain}.")
    return report


def read_all(level: list[str], domain: str, get, report: dict) -> bool:
    """Read sitemaps breadth first, following nested indexes. True if the first level held a sitemap."""
    seen = {s["url"] for s in report["sitemaps"]}
    pages = set(report["pages"])
    found_any = False
    first_level = True
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        while level:
            level = [url for url in dict.fromkeys(level) if url not in seen]
            room = MAX_FILES - len(seen)
            if room <= 0:
                report["errors"].append(f"stopped after {MAX_FILES} sitemap files; the rest weren't read")
                break
            level = level[:room]
            seen.update(level)
            results = list(pool.map(lambda url: attempt(get, url), level))
            next_level = []
            for url, (data, error) in zip(level, results):
                found = {}
                parsed = parse_sitemap(data, found) if data is not None else None
                if parsed is None:
                    if not first_level:
                        report["errors"].append(error or f"{url} isn't a sitemap")
                    continue
                found_any = found_any or first_level
                kind, locs = parsed
                entry = {"url": url, "kind": kind, "entries": len(locs)}
                report["sitemaps"].append(entry)
                for loc in locs:
                    if not on_site(loc, domain):
                        report["off_site"].append(loc)
                    elif kind == "index":
                        next_level.append(loc)
                    elif loc not in pages and len(pages) < MAX_PAGES:
                        pages.add(loc)
                        report["pages"].append(loc)
                        if loc in found:
                            report.setdefault("priorities", {})[loc] = found[loc]
            level = next_level
            first_level = False
    if len(pages) >= MAX_PAGES:
        report["errors"].append(f"stopped at {MAX_PAGES:,} pages")
    return found_any


def attempt(get, url: str) -> tuple[bytes | None, str | None]:
    try:
        return get(url), None
    except SitemapError as error:
        return None, str(error)


def save(report: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pages.txt").write_text("".join(url + "\n" for url in report["pages"]))
    priorities = report.get("priorities") or {}
    if priorities:
        (folder / "priorities.json").write_text(json.dumps(priorities) + "\n")
    meta = {k: v for k, v in report.items() if k not in ("pages", "priorities")}
    meta["with_priority"] = len(priorities)
    meta["off_site"] = sorted(set(meta["off_site"]))[:50] + (["..."] if len(set(meta["off_site"])) > 50 else [])
    meta["page_count"] = len(report["pages"])
    (folder / "sitemaps.json").write_text(json.dumps(meta, indent=2) + "\n")


def load(folder: Path) -> tuple[dict, list[str]]:
    meta_path, pages_path = folder / "sitemaps.json", folder / "pages.txt"
    if not pages_path.is_file() or not meta_path.is_file():
        raise SitemapError(f"{folder} has no pages.txt and sitemaps.json; run `fetch <site>` first.")
    return json.loads(meta_path.read_text()), pages_path.read_text().split()


def load_priorities(folder: Path) -> dict[str, float]:
    path = folder / "priorities.json"
    return json.loads(path.read_text()) if path.is_file() else {}


# ---------------------------------------------------------------- languages

def segments(url: str) -> list[str]:
    path = urllib.parse.urlparse(url).path
    parts = [urllib.parse.unquote(p).strip() for p in path.split("/")]
    parts = [p for p in parts if p]
    if parts and parts[-1].lower().endswith(PAGE_EXTENSIONS):
        parts[-1] = parts[-1].rsplit(".", 1)[0]
    if parts and parts[-1].lower() in ("index", "default"):
        parts.pop()
    return parts


def language_prefixes(urls: list[str]) -> dict[str, int]:
    """Pages per language prefix, biggest first; empty when the site doesn't split by language."""
    counts: dict[str, int] = {}
    for url in urls:
        parts = segments(url)
        match = LOCALE.match(parts[0]) if parts else None
        if match and match[1].lower() in ISO_639_1:
            key = parts[0].lower().replace("_", "-")
            counts[key] = counts.get(key, 0) + 1
    regional = [k for k in counts if "-" in k]
    if len(counts) < 3 and len(regional) < 2:
        return {}
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def pick_language(urls: list[str], prefixes: dict[str, int], wanted: str | None) -> str | None:
    """The language prefix to draw, or None for the pages without one."""
    if wanted:
        wanted = wanted.lower().replace("_", "-")
        if wanted in ("none", "root"):
            return None
        if wanted == "all":
            return "all"
        if wanted not in prefixes:
            known = ", ".join(list(prefixes)[:30]) or "none"
            raise SitemapError(f"no pages under /{wanted}/. Language prefixes on this site: {known}.")
        return wanted
    if not prefixes:
        return None
    unprefixed = len(urls) - sum(prefixes.values())
    if unprefixed >= max(prefixes.values()):
        return None
    for code in ENGLISH:
        if code in prefixes:
            return code
    english = [k for k in prefixes if k.startswith("en-")]
    return english[0] if english else next(iter(prefixes))


def in_language(url: str, prefixes: dict[str, int], language: str | None) -> list[str] | None:
    """The URL's path below its language prefix, or None when it's in another language."""
    parts = segments(url)
    head = parts[0].lower().replace("_", "-") if parts else None
    if language == "all":
        return parts
    if language is None:
        return None if head in prefixes else parts
    return parts[1:] if head == language else None


# ---------------------------------------------------------------- tree

class Node:
    __slots__ = ("segment", "parent", "children", "url", "folded", "size", "order", "priority", "virtual", "info")

    def __init__(self, segment: str, parent: Node | None = None):
        self.segment = segment
        self.parent = parent
        self.children: dict[str, Node] = {}
        self.url: str | None = None      # set when the node is a page
        self.folded = 0                  # on a fold node: how many pages it stands for
        self.size = 1                    # nodes drawn for this one and everything under it
        self.order = 0                   # where the node first comes in the sitemap
        self.priority: float | None = None   # the page's <priority> in the sitemap
        self.virtual = False             # a collection: a node the drawing adds to group siblings
        self.info: dict = {}             # on a collection: what its members have in common

    @property
    def path(self) -> str:
        parts, node = [], self
        while node.parent is not None:
            if node is self or not node.virtual:     # a page keeps its URL's path inside a collection
                parts.append(node.segment)
            node = node.parent
        # The root's segment is "" for the whole site, or the path of the section drawn on its own.
        return (node.segment + "/" + "/".join(reversed(parts))).rstrip("/") or "/"

    def pages(self) -> int:
        return self.folded + (1 if self.url else 0) + sum(c.pages() for c in self.children.values())

    def walk(self):
        yield self
        for child in self.children.values():
            yield from child.walk()


def build_tree(urls: list[str], prefixes: dict[str, int], language: str | None,
               priorities: dict[str, float] | None = None) -> Node:
    root = Node("")
    seen: list[str] = []
    for url in urls:
        parts = in_language(url, prefixes, language)
        if parts is None:
            continue
        node = root
        for part in parts:
            key = part.lower()
            if key not in node.children:
                node.children[key] = Node(part, node)
                node.children[key].order = len(seen)
                seen.append(key)
            node = node.children[key]
        if node.url is None:
            node.url = url
            node.priority = (priorities or {}).get(url)
    if not root.children and root.url is None:
        raise SitemapError("none of the sitemap's pages are in that language.")
    for node in reversed(list(root.walk())):
        node.size = 1 + sum(c.size for c in node.children.values())
    return root


def section(root: Node, path: str) -> Node:
    """The node at `path`, detached to be drawn on its own."""
    node = root
    for part in [p for p in path.strip("/").split("/") if p]:
        node = node.children.get(part.lower())
        if node is None:
            sections = ", ".join(n.path for n in display_order(root)[:20] if n.children)
            raise SitemapError(f"no section {path} in the sitemap. Sections at the top: {sections}.")
    if node is not root:
        node.segment, node.parent = node.path, None
    return node


def is_fold(node: Node) -> bool:
    return node.folded > 0 and not node.children


def natural(text: str) -> list:
    """A sort key that puts page 2 before page 10."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", text.lower())]


def display_order(node: Node) -> list[Node]:
    """Sections first, biggest first; then single pages A to Z; the fold node last."""
    return sorted(node.children.values(), key=lambda n: (is_fold(n), not n.children,
                                                         -n.pages() if n.children else 0, natural(n.segment)))


def keep_first(node: Node, keep: int, kids: list[Node] | None = None) -> None:
    """Keep the node's first `keep` children, in display order or the order given, and fold the others
    into one node that counts their pages."""
    kids = display_order(node) if kids is None else kids
    rest = kids[keep:]
    if not rest:
        return
    fold_node = Node("+", node)
    fold_node.folded = sum(k.pages() for k in rest)
    shown = {id(k) for k in kids[:keep]}
    node.children = {key: k for key, k in node.children.items() if id(k) in shown}
    node.children["+"] = fold_node


# ---------------------------------------------------------------- collections

def token_kind(token: str) -> str:
    if token.isdigit():
        return "YEAR" if len(token) == 4 and token[:2] in ("19", "20") else "N"
    digits, letters = any(c.isdigit() for c in token), any(c.isalpha() for c in token)
    if len(token) >= 8 and digits and letters:
        return "ID"
    if len(token) >= 16 and token.isalnum() and token not in (token.lower(), token.upper()):
        return "ID"
    return "w"


def shape(segment: str) -> str:
    """What a slug is made of: `globex.com` is DOMAIN, `2019-04-11-new-sidebar` is YEAR-N, `pricing` is w1,
    `how-to-write-a-brief` is w4+. Siblings with one generated shape come from one pattern."""
    segment = UUID.sub("0uuid0000", segment)
    if "." in segment and DOMAIN_SLUG.fullmatch(segment) and segment.rsplit(".", 1)[1].lower() not in FILE_TYPES:
        return "DOMAIN"
    out, words = [], 0
    for token in [t for t in re.split(r"[-_.+\s]+", segment) if t]:
        kind = token_kind(token)
        if kind == "w":
            words += 1
            continue
        if words:
            out.append(word_count(words))
            words = 0
        if not out or out[-1] != kind:
            out.append(kind)
    if words:
        out.append(word_count(words))
    if any(k in ("N", "YEAR", "ID") for k in out):     # generated: which words there are doesn't matter,
        had_words = any(k.startswith("w") for k in out)  # but whether there are some does: 3 isn't post-3
        out = [k for k in out if not k.startswith("w")]
        out = [k for i, k in enumerate(out) if not i or out[i - 1] != k] + (["w"] if had_words else [])
    return "-".join(out) or "w1"


def word_count(n: int) -> str:
    return "w1" if n == 1 else "w2" if n <= 3 else "w4+"


def generated(sig: str) -> bool:
    return bool(GENERATED & set(sig.split("-")))


def main_like(node: Node) -> bool:
    """A single page whose slug reads like a site's own page: about, pricing, contact-sales."""
    return not node.children and not node.virtual and shape(node.segment) in PLAIN


def find_collections(node: Node) -> list[tuple[str, list[Node]]]:
    """Groups of the node's children made from one pattern, as (shape, members)."""
    groups: dict[str, list[Node]] = {}
    for kid in node.children.values():
        groups.setdefault(shape(kid.segment), []).append(kid)
    found = []
    for sig, members in groups.items():
        if len(members) < (NUMBERED_MIN if sig == "N" else COLLECTION_MIN):
            continue
        if generated(sig):
            found.append((sig, members))
            continue
        # A template makes sections with the same page in each (all have /candidates). Only those count.
        sections = [m for m in members if m.children]
        names = Counter(c for m in sections for c in m.children)
        if not names:
            continue
        common, count = names.most_common(1)[0]
        if count >= COLLECTION_MIN and count >= TEMPLATE_SHARE * len(sections):
            found.append((sig, [m for m in sections if common in m.children]))
    if not found:
        return []
    leaves = [k for k in node.children.values() if not k.children]
    if node.parent is None:                  # the top level's short plain pages are main pages, never list items
        leaves = [k for k in leaves if shape(k.segment) not in PLAIN]
    in_found = {id(m) for _, members in found for m in members}
    if leaves and sum(1 for k in leaves if id(k) in in_found) > LIST_SHARE * len(leaves):
        # A list: all its pages, short titles included, but not single words (candidates, archive), which
        # are a section's own pages, nor page numbers, which make their own range ('Pages 2 to 5').
        numbered = [m for sig, members in found if sig == "N" for m in members]
        merged = {id(m): m for sig, members in found if sig != "N" for m in members}
        merged.update({id(k): k for k in leaves if shape(k.segment) not in ("w1", "N")})
        return [("list", list(merged.values()))] + ([("N", numbered)] if numbered else [])
    # Long titles are a list's mark, not a pattern of their own: next to short ones, they're one family.
    return [(sig, members) for sig, members in found if sig != "w4+"]


def group_collections(root: Node) -> list[Node]:
    """Put each collection's members under one new node, when the level has other children to set apart
    from them. Returns the collection nodes."""
    made = []
    for node in list(root.walk()):
        if node.virtual or not node.children:
            continue
        for sig, members in find_collections(node):
            if not members or len(members) == len(node.children):
                continue                     # the whole level is the pattern: nothing to set apart
            group = wrap(node, members, sig, sum(1 for k in node.children.values() if k.virtual))
            if group.info["numbers"] and not any(m.children for m in members):
                group.folded, group.children = group.pages(), {}    # 'Pages 2 to 23' says it all
            made.append(group)
    return made


def wrap(node: Node, members: list[Node], sig: str, count: int) -> Node:
    group = Node("*" if not count else f"*{count + 1}", node)
    group.virtual = True
    group.order = min(m.order for m in members)
    numbers = [int(m.segment) for m in members if m.segment.isdigit()]
    years = sorted({int(y) for m in members for y in re.findall(r"(?<!\d)(?:19|20)\d\d(?!\d)", m.segment)})
    example = sorted(members, key=lambda m: (-m.pages(), m.segment.isdigit(), m.order))[0]
    if sig == "list":
        sig = Counter(shape(m.segment) for m in members).most_common(1)[0][0]
    group.info = {"shape": sig, "members": len(members), "example": example, "all": list(members),
                  "numbers": (min(numbers), max(numbers)) if len(numbers) == len(members) else None,
                  "years": (years[0], years[-1]) if years and "YEAR" in sig else None}
    ids = {id(m) for m in members}
    node.children = {key: k for key, k in node.children.items() if id(k) not in ids}
    for m in sorted(members, key=lambda m: m.order):
        m.parent = group
        group.children[m.segment.lower()] = m
    node.children[group.segment] = group
    return group


# ---------------------------------------------------------------- layout

def uses_priority(root: Node) -> bool:
    """Whether the sitemap ranks its pages: most pages have a <priority>, and not all the same one."""
    values = [n.priority for n in root.walk() if n.url]
    known = [v for v in values if v is not None]
    return len(known) >= 0.5 * len(values) and len(set(known)) >= 2


def ranked(node: Node) -> float:
    """A node's <priority>: its own page's, or else its best child's."""
    if node.priority is not None:
        return node.priority
    known = [c.priority for c in node.children.values() if c.priority is not None]
    return max(known, default=0.0)


def child_order(node: Node, by_priority: bool) -> list[Node]:
    """The order a node's children get drawn in. When the sitemap ranks its pages, its ranking comes first:
    it's the site's own say on what matters. Then sections and collections, biggest first, so the drawing
    keeps the site's structure; then single pages that read like main pages, in sitemap order."""
    rank = (lambda n: -ranked(n)) if by_priority else (lambda n: 0)
    return sorted(node.children.values(), key=lambda k: (rank(k), not k.children, -k.pages() if k.children else 0,
                                                         not main_like(k), k.order))


def layout(root: Node, limit: int = DEFAULT_LIMIT, per_level: int = PER_LEVEL,
           by_priority: bool = False) -> list[tuple[str, int]]:
    """Choose what to draw, top down, in at most `limit` nodes.

    Each level is filled before the next one starts, so the top of the site always shows. Under any node,
    at most `per_level` children, in child_order; the others become one 'and N other pages' node. When a
    level doesn't fit, sections share the budget by the square root of their size, so big sections show
    more and small ones still show some. Every drawn node with children keeps one node in reserve, for
    its first child or the count of its pages, so nothing disappears without being counted.
    Returns the count nodes, as (path of their section, pages)."""
    order: dict[int, list[Node]] = {}
    shown: dict[int, int] = {}
    budget = limit - 1 - (1 if root.children else 0)
    level = [root] if root.children else []
    while level:
        for parent in level:
            order[id(parent)] = child_order(parent, by_priority)
            shown[id(parent)] = 0
        weight = [math.sqrt(max(parent.pages(), 1)) for parent in level]
        queue = [(0.0, i) for i in range(len(level))]
        next_level = []
        while queue:
            _, i = heapq.heappop(queue)
            parent = level[i]
            kids, k = order[id(parent)], shown[id(parent)]
            if k >= min(len(kids), per_level):
                continue
            child = kids[k]
            # One more node, unless it's the last hidden child (its count node goes); plus the child's reserve.
            cost = (0 if k + 1 == len(kids) else 1) + (1 if child.children else 0)
            if cost > budget:
                continue
            budget -= cost
            shown[id(parent)] = k + 1
            if child.children:
                next_level.append(child)
            heapq.heappush(queue, ((k + 1) / weight[i], i))
        level = next_level
    for node in list(root.walk()):
        if id(node) in order:
            keep_first(node, shown[id(node)], order[id(node)])
            if node.virtual and list(node.children) == ["+"]:     # 'Release notes: 107' needs no '107 pages'
                node.folded, node.children = node.children["+"].folded, {}
    for node in reversed(list(root.walk())):
        node.size = 1 + sum(c.size for c in node.children.values())
    return [(n.parent.path, n.folded) for n in root.walk() if is_fold(n)]


# ---------------------------------------------------------------- labels and output

def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", UNSAFE.sub(" ", text)).strip()
    if len(text) > MAX_LABEL:
        text = text[:MAX_LABEL].rsplit(" ", 1)[0].rstrip(" ,.:-") + "..."
    return text or "Page"


def label_from(segment: str, words_fixed: dict[str, str] | None = None) -> str:
    if shape(segment) == "DOMAIN":
        return clean(segment.lower())                     # a site's name, as written: acme-labs.com
    words = re.sub(r"[-_+\s]+", " ", segment).split()
    plain = [w for w in words if token_kind(w) != "ID"]
    words = plain if plain else words                     # 'Quarterly OKRs 5pegpQuUnn...' reads 'Quarterly OKRs'
    out = []
    for i, word in enumerate(words):
        lower = word.lower()
        if lower in ACRONYMS:
            out.append(ACRONYMS[lower])
        elif word.isalpha() and word.islower():
            out.append(lower if i and lower in SMALL_WORDS else word.capitalize())
        else:
            out.append(word)
    text = " ".join(out)
    for word, fixed in (words_fixed or {}).items():
        text = re.sub(r"(?<!\w)" + re.escape(word) + r"(?!\w)", fixed.replace("\\", "\\\\"), text, flags=re.I)
    return clean(text)


def collection_label(node: Node, labels: dict[str, str]) -> str:
    """'globex.com and 261 others', 'Pages 2 to 23', '255 pages, 2019 to 2026', or the name in labels.json
    with how many it groups."""
    info, members = node.info, node.info["members"]
    if node.path.lower() in labels:
        return clean(f"{labels[node.path.lower()]}: {members:,}")
    if info.get("numbers"):
        low, high = info["numbers"]
        return f"Pages {low} to {high}" if high - low + 1 == members else f"{members:,} pages, {low} to {high}"
    if info.get("years"):
        first, last = info["years"]
        return f"{members:,} pages, {first}" + (f" to {last}" if last != first else "")
    words = {k: v for k, v in labels.items() if not k.startswith("/")}
    return clean(f"{label_from(info['example'].segment, words)} and {members - 1:,} others")


def label(node: Node, labels: dict[str, str], root_label: str) -> str:
    if node.virtual:
        return collection_label(node, labels)
    if is_fold(node):
        pages = f"{node.folded:,} page{'s' if node.folded != 1 else ''}"
        if len(node.parent.children) == 1:
            return pages
        return f"and {node.folded:,} other page{'s' if node.folded != 1 else ''}"
    path = node.path.lower()
    if path in labels:
        return clean(labels[path])
    words = {k: v for k, v in labels.items() if not k.startswith("/")}
    return clean(root_label) if node.parent is None else label_from(node.segment, words)


def ordered(node: Node, labels: dict[str, str], root_label: str) -> list[Node]:
    """As display_order, with single pages sorted by their labels."""
    return sorted(node.children.values(), key=lambda n: (is_fold(n), not n.children,
                                                         -n.pages() if n.children else 0,
                                                         natural(label(n, labels, root_label))))


def mindmap(root: Node, labels: dict[str, str], root_label: str, link: str | None = None,
            icon: str | None = None) -> str:
    """An indented outline. The root line can link to the site and carry an icon from Whimsical's set."""
    first = label(root, labels, root_label)
    if link:
        first = f"[{first}]({link})"
    lines = [first + (f" icon-name:{icon}" if icon else "")]
    for node, depth in outline(root, labels, root_label)[1:]:
        lines.append("  " * (depth - 1) + "- " + label(node, labels, root_label))
    return "\n".join(lines) + "\n"


def outline(root: Node, labels: dict[str, str], root_label: str) -> list[tuple[Node, int]]:
    """Every node with its depth, in the order the mind map's lines list them: the root first."""
    out = [(root, 0)]

    def add(node: Node, depth: int) -> None:
        for kid in ordered(node, labels, root_label):
            out.append((kid, depth))
            add(kid, depth + 1)
    add(root, 1)
    return out


def crowded(node: Node, over: int) -> bool:
    """A list worth collapsing: more than `over` children, mostly single pages, or a collection. A node
    whose children are mostly sections stays open, so the site's structure shows."""
    kids = list(node.children.values())
    if node.parent is None or len(kids) <= over:
        return False
    return node.virtual or sum(1 for k in kids if not k.children) > len(kids) / 2


def collapsed_lines(root: Node, labels: dict[str, str], root_label: str, over: int) -> list[int]:
    """Which nodes of the mind map start collapsed, as line numbers of mindmap.md (the root is 1)."""
    if over <= 0:
        return []
    return [i + 1 for i, (node, _) in enumerate(outline(root, labels, root_label)) if crowded(node, over)]


def left_branches(root: Node, labels: dict[str, str], root_label: str, over: int = 0) -> list[int]:
    """Which top-level branches of the mind map to put left of the root, counted from 1 in the order
    they come, so both sides have about as many rows. Whimsical puts them all on the right. A node that
    starts collapsed takes one row."""
    def rows(node: Node) -> int:
        if over > 0 and crowded(node, over):
            return 1
        return max(1, sum(rows(c) for c in node.children.values()))
    branches = ordered(root, labels, root_label)
    sides = [0, 0]                           # rows on the right, on the left
    left = []
    for i in sorted(range(len(branches)), key=lambda i: -rows(branches[i])):
        side = 1 if sides[1] < sides[0] else 0
        sides[side] += rows(branches[i])
        if side:
            left.append(i + 1)
    if len(left) > len(branches) / 2:        # the mirror image is as balanced and takes fewer moves
        left = [i for i in range(1, len(branches) + 1) if i not in left]
    return sorted(left)


def ranges(numbers: list[int]) -> str:
    """[1, 2, 3, 5] as '1 to 3, 5'."""
    out, start = [], None
    for i, n in enumerate(numbers):
        start = n if start is None else start
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            out.append(str(n) if n == start else f"{start}, {n}" if n == start + 1 else f"{start} to {n}")
            start = None
    return ", ".join(out)


def flowchart(root: Node, labels: dict[str, str], root_label: str) -> str:
    """A Mermaid class diagram: a table per section, its single pages as rows, an arrow to each subsection."""
    lines = ["classDiagram", "  direction TB"]
    edges = []
    ids: dict[int, str] = {}

    def add(node: Node) -> None:
        ids[id(node)] = f"n{len(ids)}"
        kids = ordered(node, labels, root_label)
        rows = [label(k, labels, root_label) for k in kids if not k.children]
        name = label(node, labels, root_label).replace('"', "'")
        if rows:
            lines.append(f'  class {ids[id(node)]}["{name}"] {{')
            lines.extend(f"    {row}" for row in rows)
            lines.append("  }")
        else:
            lines.append(f'  class {ids[id(node)]}["{name}"]')
        for kid in kids:
            if kid.children:
                add(kid)
                edges.append(f"  {ids[id(node)]} --> {ids[id(kid)]}")
    add(root)
    return "\n".join(lines + edges) + "\n"


def read_labels(folder: Path) -> dict[str, str]:
    path = folder / "labels.json"
    if not path.is_file():
        return {}
    try:
        labels = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise SitemapError(f"{path} isn't valid JSON: {error}") from None
    if not isinstance(labels, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str)
                                               for k, v in labels.items()):
        raise SitemapError(f'{path} must map paths or words to names, like '
                           f'{{"/": "Acme", "/hr-software": "HR Software", "acmepay": "AcmePay"}}.')
    # Paths ("/careers") name one node; words ("geforce") fix that word in every label made from a URL.
    paths = {("/" + k.strip("/")).lower(): v for k, v in labels.items() if k.startswith("/")}
    words = {k.strip().lower(): v for k, v in labels.items() if not k.startswith("/")}
    return {**dict(sorted(words.items(), key=lambda kv: -len(kv[0]))), **paths}


# ---------------------------------------------------------------- commands

def summary(meta: dict, urls: list[str], language: str | None = None, wanted: str | None = None) -> list[str]:
    prefixes = language_prefixes(urls)
    language = pick_language(urls, prefixes, wanted)
    files = len(meta.get("sitemaps", []))
    out = [f"{meta['domain']}: {len(urls):,} URLs in {files} sitemap file{'s' if files != 1 else ''}."]
    if prefixes:
        shown = ", ".join(f"/{k}/ ({v:,})" for k, v in list(prefixes.items())[:8])
        more = f" and {len(prefixes) - 8} more" if len(prefixes) > 8 else ""
        which = "the pages without a language prefix" if language is None else \
            "every language" if language == "all" else f"/{language}/"
        out.append(f"Languages: {len(prefixes)} versions: {shown}{more}. Drawing {which}; "
                   "pick another with --locale CODE (or none, or all).")
    root = build_tree(urls, prefixes, language)
    sections = ordered(root, {}, meta["domain"])
    total = root.pages()
    top = ", ".join(f"{label_from(n.segment)} ({n.pages():,})" for n in sections[:12] if not is_fold(n))
    more = f", and {len(sections) - 12} more" if len(sections) > 12 else ""
    out.append(f"In it: {total:,} pages, {len(sections)} top-level sections and pages: {top}{more}.")
    depth = max((len(n.path.strip("/").split("/")) for n in root.walk() if n.parent), default=0)
    out.append(f"Unfolded, the tree has {root.size:,} nodes and {depth} levels.")
    for error in meta.get("errors", [])[:10]:
        out.append(f"warning: {error}")
    if len(meta.get("errors", [])) > 10:
        out.append(f"warning: and {len(meta['errors']) - 10} more problems, listed in sitemaps.json")
    return out


def note_info(meta: dict, language: str | None, root: Node, pages: int, folds: list[tuple[str, int]]) -> dict:
    """What the text above the drawing says about the sitemap, saved in note.json for `note`."""
    where = root.path if root.path != "/" else ""
    if language not in (None, "all"):
        where = f"/{language}{where}"
    return {"sitemap": (meta.get("sitemaps") or [{"url": meta["site"]}])[0]["url"], "domain": meta["domain"],
            "read": meta.get("fetched_at") or meta.get("fetched"), "where": where, "pages": pages,
            "counted": sum(count for _, count in folds)}


def when(stamp: str) -> str:
    """2026-11-25T14:05+01:00 as '25 Nov 2026 at 14:05'; a bare date as '25 Nov 2026'."""
    moment = datetime.fromisoformat(stamp)
    day = f"{moment.day} {moment:%b %Y}"
    return day if "T" not in stamp else f"{day} at {moment:%H:%M}"


def plural(n: int, word: str) -> str:
    return f"**{n:,}** {word}{'s' if n != 1 else ''}"


def root_link(meta: dict, root: Node, language: str | None) -> str:
    """The address the root node links to: the page it stands for, or the site."""
    url = root.url
    if not url:
        prefix = f"/{language}" if language not in (None, "all") else ""
        url = meta["site"] + prefix + (root.path if root.path != "/" else "")
    return urllib.parse.quote(url, safe=":/?#@!$&'*+,;=%").replace("(", "%28").replace(")", "%29")


def cmd_fetch(args) -> None:
    _, domain = site_of(args.site)
    folder = Path(args.out or "sitemaps") / domain
    if (folder / "pages.txt").is_file() and not args.refresh:
        meta, urls = load(folder)
        print(f"Already fetched on {meta.get('fetched')}: reading {folder}/pages.txt (--refresh to fetch again).")
    else:
        report = fetch_site(args.site)
        save(report, folder)
        meta, urls = load(folder)
        print(f"Saved {len(urls):,} pages in {folder}/pages.txt.")
    print("\n".join(summary(meta, urls)))


def cmd_draw(args) -> None:
    folder = Path(args.folder)
    meta, urls = load(folder)
    if not 2 <= args.limit <= MAX_LIMIT:
        raise SitemapError(f"--limit must be between 2 and {MAX_LIMIT}, the most the Whimsical MCP takes in one "
                           "mind map.")
    if args.type != "mindmap" and args.limit > MAX_FLOWCHART:
        raise SitemapError(f"a flowchart takes at most {MAX_FLOWCHART:,} nodes in the Whimsical MCP: use --limit "
                           f"{MAX_FLOWCHART} or less, or draw only the mind map with more.")
    if args.collapse_over < 0:
        raise SitemapError("--collapse-over takes a number of pages, or 0 to keep every node open.")
    if not 1 <= args.per_level < MAX_ROWS:
        raise SitemapError(f"--per-level must be between 1 and {MAX_ROWS - 1}, the most rows a flowchart table "
                           "takes, with the 'other pages' row.")
    if args.icon and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.icon):
        raise SitemapError(f"--icon takes an icon name from Whimsical's set, like logo-github, not {args.icon!r}.")
    prefixes = language_prefixes(urls)
    language = pick_language(urls, prefixes, args.locale)
    labels = read_labels(folder)
    priorities = load_priorities(folder)
    kinds = ["mindmap", "flowchart"] if args.type == "both" else [args.type]
    for kind in kinds:
        root = build_tree(urls, prefixes, language, priorities)
        if args.section:
            root = section(root, args.section)
            words = {k: v for k, v in labels.items() if not k.startswith("/")}
            root_label = labels.get(root.path.lower(), label_from(root.path.rsplit("/", 1)[-1], words))
        else:
            root_label = labels.get("/", meta["domain"])
        pages = root.pages()
        by_priority = uses_priority(root)
        groups = group_collections(root)
        folds = layout(root, args.limit, args.per_level, by_priority)
        link = root_link(meta, root, language)
        if kind == "mindmap":
            text = mindmap(root, labels, root_label, link, args.icon)
        else:
            text = flowchart(root, labels, root_label)
        if len(text) > MAX_TEXT:
            raise SitemapError(f"the {kind} is {len(text):,} characters, over the Whimsical MCP's {MAX_TEXT:,}; "
                               "draw it again with a lower --limit.")
        out = folder / ("mindmap.md" if kind == "mindmap" else "flowchart.mmd")
        out.write_text(text)
        print(f"Wrote {out}: {len(text):,} characters, about {len(text) // 4:,} tokens.")
        if kind == "flowchart":
            icon = f', "icon_name": "{args.icon}"' if args.icon else ""
            print(f'Flowchart root: set the root table\'s header to {{"row": 0, "col": 0, '
                  f'"text": "[{label(root, labels, root_label)}]({link})"{icon}}}.'
                  + (' With the logo, also widen it: "widths": [<the root table\'s width plus 60>].' if icon else ""))
        left = left_branches(root, labels, root_label, args.collapse_over) if kind == "mindmap" else []
        shut = collapsed_lines(root, labels, root_label, args.collapse_over) if kind == "mindmap" else []
        if shut:
            print(f"Mind map collapsed: nodes {ranges(shut)} ({len(shut)} of {root.size}, by their line in "
                  f"mindmap.md, the root is 1): the lists of more than {args.collapse_over} pages start closed.")
        if left:
            print(f"Mind map sides: put top-level branches {ranges(left)} on the left "
                  f"(of {len(root.children)}, counted from 1 in order).")
        hidden = sum(p for _, p in folds)
        print(f"{pages:,} pages, {pages - hidden:,} of them drawn, in {root.size:,} nodes (limit {args.limit:,}).")
        if folds:
            big = ", ".join(f"{path} ({count:,})" for path, count in sorted(folds, key=lambda f: -f[1])[:6])
            print(f"Counted, not drawn: {hidden:,} pages in {len(folds)} 'other pages' node"
                  f"{'s' if len(folds) != 1 else ''}, the biggest under {big}{', ...' if len(folds) > 6 else ''}.")
        print("Priority: the sitemap ranks its pages, so the drawing follows its ranking first." if by_priority
              else "Priority: not used (the sitemap doesn't rank its pages).")
        info = note_info(meta, language, root, pages, folds)
    (folder / "note.json").write_text(json.dumps(info))
    unknown = sorted({k for k in labels if k.startswith("/")} - {n.path.lower() for n in root.walk()} - {"/"})
    print("Top level, as labelled (fix them in labels.json, by path or by word):")
    print(f"  {root.path} -> {label(root, labels, root_label)}")
    for kid in ordered(root, labels, root_label):
        if not is_fold(kid):
            count = kid.pages()
            print(f"  {kid.path} -> {label(kid, labels, root_label)} ({count:,} page{'s' if count != 1 else ''}"
                  f"{', a collection' if kid.virtual else ''})")
    if groups:
        print(f"Collections, pages made from one pattern, grouped in {len(groups)} node"
              f"{'s' if len(groups) != 1 else ''} (name them in labels.json, by path):")
        for group in sorted(groups, key=lambda g: -g.pages())[:15]:
            if group.parent is None and group is not root:
                continue
            examples = sorted(group.info["all"], key=lambda m: m.order)[:5]
            words = {k: v for k, v in labels.items() if not k.startswith("/")}
            print(f"  {group.path} -> {label(group, labels, root_label)} "
                  f"({group.pages():,} pages, shape {group.info['shape']}; e.g. "
                  + ", ".join(label_from(m.segment, words) for m in examples) + ")")
        if len(groups) > 15:
            print(f"  and {len(groups) - 15} more")
    for path in unknown:
        print(f"warning: labels.json names {path}, which isn't in the drawing")


def cmd_note(args) -> None:
    """The text to put above the drawing once it's done: the sitemap it read, and what's shown."""
    note_path = Path(args.folder) / "note.json"
    if not note_path.is_file():
        raise SitemapError("run `draw` first: the note describes what it drew.")
    f = json.loads(note_path.read_text())
    shown = f["pages"] - f["counted"]
    pages = plural(f["pages"], "page") + (f" in {f['where']}" if f["where"] else "")
    what = f"{pages}, **{shown:,}** of them drawn." if f["counted"] else f"{pages}, all drawn."
    print(f"[Sitemap of **{f['domain']}**]({f['sitemap']}), read on {when(f['read'])}.")
    print(what)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fetch", help="find and read the site's sitemaps")
    p.add_argument("site")
    p.add_argument("--out", help="parent folder for the site's folder (default: sitemaps)")
    p.add_argument("--refresh", action="store_true", help="fetch again even if pages.txt exists")
    p.set_defaults(run=cmd_fetch)
    p = sub.add_parser("draw", help="write the mind map or flowchart text")
    p.add_argument("folder")
    p.add_argument("--type", choices=["mindmap", "flowchart", "both"], required=True)
    p.add_argument("--locale", help="language prefix to draw, like en-us; none for unprefixed pages; all")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="most nodes to draw (default 1000)")
    p.add_argument("--section", help="draw only this section, like /blog")
    p.add_argument("--collapse-over", type=int, default=COLLAPSE_OVER,
                   help="in the mind map, collapse lists of more pages than this (default 8; 0 keeps all open)")
    p.add_argument("--icon", help="icon for the root, from Whimsical's set, like logo-github")
    p.add_argument("--per-level", type=int, default=PER_LEVEL,
                   help="most children shown under any node; the rest become 'and N other pages' (default 30)")
    p.set_defaults(run=cmd_draw)
    p = sub.add_parser("note", help="print the text to put above the drawing")
    p.add_argument("folder")
    p.set_defaults(run=cmd_note)
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except SitemapError as error:
        print(f"sitemap: {error}", file=sys.stderr)
        sys.exit(NOT_FOUND if isinstance(error, NoSitemap) else 1)


if __name__ == "__main__":
    main()
