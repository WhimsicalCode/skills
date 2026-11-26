import ast
import gzip
import json
import re

import pytest
import sitemap
from conftest import SCRIPT, fake_web, index, run_script, urlset

SITE = "https://www.acme.com"


def acme(blog=0, docs=(), extra=()):
    """Page URLs of a fictional site: a few top pages, `blog` posts, and docs sections of given sizes."""
    urls = [f"{SITE}/", f"{SITE}/pricing", f"{SITE}/about", f"{SITE}/blog"]
    urls += [f"{SITE}/blog/post-{i:04d}" for i in range(blog)]
    for s, size in enumerate(docs):
        urls += [f"{SITE}/docs/section-{s}/page-{i:04d}" for i in range(size)]
    return urls + list(extra)


def tree(urls, language=None):
    prefixes = sitemap.language_prefixes(urls)
    return sitemap.build_tree(urls, prefixes, sitemap.pick_language(urls, prefixes, language))


def drawn_pages(root):
    """Pages the tree still shows, plus the pages its fold nodes stand for."""
    return sum((1 if n.url else 0) + n.folded for n in root.walk())


def real_size(root):
    return sum(1 for _ in root.walk())


# ---------------------------------------------------------------- addresses

@pytest.mark.parametrize("text,origin,domain", [
    ("acme.com", "https://acme.com", "acme.com"),
    ("https://WWW.Acme.com/en-us/products", "https://www.acme.com", "acme.com"),
    ("http://shop.acme.co.uk", "http://shop.acme.co.uk", "shop.acme.co.uk"),
])
def test_site_of(text, origin, domain):
    assert sitemap.site_of(text) == (origin, domain)


@pytest.mark.parametrize("text", ["acme", "ftp://acme.com", "https://user@acme.com", "https://acme.com:8443", ""])
def test_site_of_refuses_what_isnt_a_website(text):
    with pytest.raises(sitemap.SitemapError, match="not a website address"):
        sitemap.site_of(text)


def test_on_site_keeps_to_the_domain_and_its_subdomains():
    assert sitemap.on_site("https://www.acme.com/a", "acme.com")
    assert sitemap.on_site("https://docs.acme.com/a", "acme.com")
    assert not sitemap.on_site("https://acme.com.evil.test/a", "acme.com")
    assert not sitemap.on_site("https://notacme.com/a", "acme.com")
    assert not sitemap.on_site("https://user@acme.com/a", "acme.com")
    assert not sitemap.on_site("https://acme.com:8080/a", "acme.com")
    assert not sitemap.on_site("file:///etc/passwd", "acme.com")


def test_redirects_off_the_site_are_refused():
    import urllib.request
    handler = sitemap.StayOnSite("acme.com")
    request = urllib.request.Request("https://acme.com/sitemap.xml")
    with pytest.raises(sitemap.SitemapError, match="redirects off the site"):
        handler.redirect_request(request, None, 302, "Found", {}, "https://globex.com/sitemap.xml")
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://www.acme.com/sitemap.xml")


# ---------------------------------------------------------------- reading sitemaps

def test_parse_urlset_and_index():
    assert sitemap.parse_sitemap(urlset(f"{SITE}/a", f"{SITE}/b")) == ("pages", [f"{SITE}/a", f"{SITE}/b"])
    assert sitemap.parse_sitemap(index(f"{SITE}/s1.xml")) == ("index", [f"{SITE}/s1.xml"])


def test_parse_ignores_image_locs_inside_entries():
    data = (f'<urlset {sitemap_ns()} xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
            f"<url><loc>{SITE}/a</loc><image:image><image:loc>{SITE}/a.png</image:loc></image:image></url>"
            "</urlset>").encode()
    assert sitemap.parse_sitemap(data) == ("pages", [f"{SITE}/a"])


def sitemap_ns():
    return 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def test_parse_text_sitemap_and_refuse_html():
    assert sitemap.parse_sitemap(f"{SITE}/a\n{SITE}/b\n".encode()) == ("pages", [f"{SITE}/a", f"{SITE}/b"])
    assert sitemap.parse_sitemap(b"<!doctype html><html><body>Not found</body></html>") is None
    assert sitemap.parse_sitemap(b"User-agent: *\nDisallow: /") is None
    assert sitemap.parse_sitemap(b"<urlset><url><loc>broken") is None


def test_fetch_follows_robots_and_nested_indexes():
    web = fake_web({
        f"{SITE.replace('www.', '')}/robots.txt": f"User-agent: *\nSitemap: {SITE}/sitemap_index.xml\n".encode(),
        f"{SITE}/sitemap_index.xml": index(f"{SITE}/pages.xml", f"{SITE}/blog-index.xml",
                                           "https://cdn.globex.com/sitemap.xml"),
        f"{SITE}/pages.xml": urlset(f"{SITE}/", f"{SITE}/pricing", "https://globex.com/elsewhere"),
        f"{SITE}/blog-index.xml": index(f"{SITE}/blog.xml", f"{SITE}/missing.xml"),
        f"{SITE}/blog.xml": urlset(f"{SITE}/blog/one", f"{SITE}/blog/two", f"{SITE}/pricing"),
    })
    report = sitemap.fetch_site("acme.com", get=web)
    assert report["pages"] == [f"{SITE}/", f"{SITE}/pricing", f"{SITE}/blog/one", f"{SITE}/blog/two"]
    assert "https://cdn.globex.com/sitemap.xml" in report["off_site"]
    assert "https://globex.com/elsewhere" in report["off_site"]
    assert any("missing.xml" in e for e in report["errors"])
    assert len(report["sitemaps"]) == 4


def test_fetch_falls_back_to_the_usual_places():
    web = fake_web({"https://acme.com/sitemap_index.xml": urlset("https://acme.com/a")})
    assert sitemap.fetch_site("acme.com", get=web)["pages"] == ["https://acme.com/a"]


def test_fetch_reads_text_sitemaps_listed_in_robots():
    web = fake_web({"https://acme.com/robots.txt": b"Sitemap: https://acme.com/sitemap.txt",
                    "https://acme.com/sitemap.txt": b"https://acme.com/a\nhttps://acme.com/b"})
    assert len(sitemap.fetch_site("acme.com", get=web)["pages"]) == 2


def test_no_sitemap():
    web = fake_web({"https://acme.com/robots.txt": b"User-agent: *\n",
                    "https://acme.com/sitemap.xml": b"<!doctype html><title>Acme</title>"})
    with pytest.raises(sitemap.NoSitemap, match="No sitemap found on acme.com"):
        sitemap.fetch_site("acme.com", get=web)


def test_sitemap_without_pages_on_the_site():
    web = fake_web({"https://acme.com/sitemap.xml": urlset("https://globex.com/a")})
    with pytest.raises(sitemap.NoSitemap, match="lists no pages"):
        sitemap.fetch_site("acme.com", get=web)


def test_gzipped_sitemaps_are_unzipped(monkeypatch):
    body = gzip.compress(urlset("https://acme.com/a"))

    class Response:
        def __init__(self, data):
            self.data = data

        def read(self, n):
            return self.data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("User-agent").startswith("WhimsicalSitemapSkill")
            return Response(body)

    monkeypatch.setattr(sitemap.urllib.request, "build_opener", lambda *handlers: Opener())
    get = sitemap.http_get("acme.com")
    assert sitemap.parse_sitemap(get("https://acme.com/sitemap.xml.gz")) == ("pages", ["https://acme.com/a"])
    with pytest.raises(sitemap.SitemapError, match="isn't on acme.com"):
        get("https://globex.com/sitemap.xml")


# ---------------------------------------------------------------- languages

def test_language_prefixes_need_several_versions():
    urls = [f"{SITE}/{code}/page" for code in ("en-us", "de-de", "fr-fr")] + [f"{SITE}/it/services"]
    assert set(sitemap.language_prefixes(urls)) == {"en-us", "de-de", "fr-fr", "it"}
    assert sitemap.language_prefixes([f"{SITE}/it/services", f"{SITE}/id/login", f"{SITE}/pricing"]) == {}


def test_english_is_drawn_when_every_page_has_a_prefix():
    urls = [f"{SITE}/{code}/p{i}" for code in ("de-de", "en-us", "fr-fr") for i in range(3)]
    prefixes = sitemap.language_prefixes(urls)
    assert sitemap.pick_language(urls, prefixes, None) == "en-us"
    assert sitemap.pick_language(urls, prefixes, "DE_de") == "de-de"
    with pytest.raises(sitemap.SitemapError, match="no pages under /ja-jp/"):
        sitemap.pick_language(urls, prefixes, "ja-jp")


def test_unprefixed_pages_win_when_they_are_the_biggest_version():
    urls = acme(blog=20) + [f"{SITE}/{code}/pricing" for code in ("de", "fr", "es")]
    prefixes = sitemap.language_prefixes(urls)
    assert sitemap.pick_language(urls, prefixes, None) is None
    root = sitemap.build_tree(urls, prefixes, None)
    assert "de" not in root.children and "blog" in root.children


def test_all_languages_keeps_prefixes_as_sections():
    urls = [f"{SITE}/{code}/p" for code in ("de-de", "en-us", "fr-fr")]
    root = tree(urls, "all")
    assert set(root.children) == {"de-de", "en-us", "fr-fr"}


# ---------------------------------------------------------------- tree and layout

def test_tree_merges_trailing_slashes_index_pages_and_extensions():
    root = tree([f"{SITE}/docs/", f"{SITE}/docs/index.html", f"{SITE}/docs/start.html", f"{SITE}/docs/start",
                 f"{SITE}/Docs/Start?ref=nav"])
    assert list(root.children) == ["docs"]
    assert list(root.children["docs"].children) == ["start"]
    assert root.pages() == 2


def test_small_site_is_drawn_whole():
    root = tree(acme(blog=10))
    assert sitemap.layout(root) == []
    assert root.size == real_size(root) == 14


def test_layout_stays_within_the_limit_and_counts_every_page():
    root = tree(acme(blog=900, docs=(300, 120, 40, 8)))
    total = root.pages()
    sitemap.layout(root, 200)
    assert root.size == real_size(root) <= 200
    assert drawn_pages(root) == total


def test_nothing_disappears_without_a_count_even_on_a_tiny_budget():
    root = tree(acme(blog=50, docs=[20] * 12))
    total = root.pages()
    sitemap.layout(root, 6)
    assert real_size(root) <= 6 and drawn_pages(root) == total


def test_each_level_is_filled_before_the_next():
    urls = [f"{SITE}/about"] + [f"{SITE}/s{i:02d}/p{j}" for i in range(40) for j in range(50)]
    root = tree(urls)
    sitemap.layout(root, 100)
    assert len(root.children) == 31                           # 30 shown and 'and N other pages'
    assert all(len(k.children) >= 1 for k in root.children.values() if not sitemap.is_fold(k))


def test_each_level_shows_at_most_30_children():
    root = tree(acme(blog=330))
    sitemap.layout(root)
    blog = root.children["blog"]
    assert len(blog.children) == 31
    assert sitemap.label(sitemap.display_order(blog)[-1], {}, "Acme") == "and 300 other pages"


def test_big_sections_get_more_room_and_small_ones_still_show():
    root = tree(acme(docs=(400, 25)))
    sitemap.layout(root, 40)
    docs = root.children["docs"]
    big, small = docs.children["section-0"], docs.children["section-1"]
    assert len(big.children) > len(small.children) >= 2


def test_sections_first_then_pages_that_read_like_main_pages():
    urls = [f"{SITE}/how-we-built-our-new-office", f"{SITE}/pricing", f"{SITE}/about"]
    urls += [f"{SITE}/s{i:02d}/page" for i in range(28)]
    root = tree(urls)
    sitemap.layout(root)
    kept = set(root.children)
    assert {f"s{i:02d}" for i in range(28)} <= kept
    assert {"pricing", "about"} <= kept and "how-we-built-our-new-office" not in kept


def test_the_sitemaps_priority_comes_first_when_it_ranks_pages():
    urls = [f"{SITE}/s{i:02d}/page" for i in range(30)] + [f"{SITE}/store", f"{SITE}/legal-notice"]
    priorities = {u: 0.5 for u in urls} | {f"{SITE}/store": 0.9}
    root = sitemap.build_tree(urls, {}, None, priorities)
    assert sitemap.uses_priority(root)
    sitemap.layout(root, by_priority=True)
    assert "store" in root.children and "legal-notice" not in root.children
    same = sitemap.build_tree(urls, {}, None, {u: 0.5 for u in urls})
    assert not sitemap.uses_priority(same)


def test_parse_reads_priorities():
    data = (f"<urlset {sitemap_ns()}><url><loc>{SITE}/a</loc><priority>0.8</priority></url>"
            f"<url><loc>{SITE}/b</loc><priority>Acme</priority></url><url><loc>{SITE}/c</loc></url></urlset>").encode()
    found = {}
    assert sitemap.parse_sitemap(data, found) == ("pages", [f"{SITE}/a", f"{SITE}/b", f"{SITE}/c"])
    assert found == {f"{SITE}/a": 0.8}


# ---------------------------------------------------------------- collections

@pytest.mark.parametrize("segment,sig", [
    ("clickup.com", "DOMAIN"),
    ("2", "N"),
    ("2019-04-11-new-sidebar", "YEAR-N-w"),
    ("2020-06-30", "YEAR-N"),
    ("post-3", "N-w"),
    ("pricing", "w1"),
    ("contact-sales", "w2"),
    ("how-to-write-a-brief", "w4+"),
    ("quarterly-okrs-5pegpQuUnnsmRsoEYiaWxh", "ID-w"),
    ("069c4628-88d7-4e4d-b393-c99637ab0123", "ID"),
    ("annual-report.pdf", "w2"),
])
def test_shape(segment, sig):
    assert sitemap.shape(segment) == sig


def drawn_tree(urls):
    root = tree(urls)
    groups = sitemap.group_collections(root)
    return root, groups


def test_a_directory_of_sites_is_one_collection_and_the_main_pages_stay():
    urls = [f"{SITE}/", f"{SITE}/about", f"{SITE}/methodology", f"{SITE}/companies"]
    urls += [f"{SITE}/acme-{i:02d}.com/candidates" for i in range(20)]
    urls += [f"{SITE}/globex-{i:02d}.io" for i in range(10)]
    root, groups = drawn_tree(urls)
    assert set(root.children) == {"about", "methodology", "companies", "*"}
    assert sitemap.label(root.children["*"], {}, "Acme") == "acme-00.com and 29 others"
    assert root.children["*"].children["acme-00.com"].path == "/acme-00.com"   # pages keep their path


def test_sections_made_from_one_template_form_a_collection():
    urls = [f"{SITE}/{name}/legal" for name in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
                                                 "golf", "hotel", "india")]
    urls += [f"{SITE}/payments/{i}" for i in ("checkout", "links")] + [f"{SITE}/pricing"]
    root, groups = drawn_tree(urls)
    assert set(root.children) == {"payments", "pricing", "*"}
    assert len(root.children["*"].children) == 9


def test_numbered_pages_become_one_range():
    urls = [f"{SITE}/acme.com/{i}" for i in range(2, 10)] + [f"{SITE}/acme.com/candidates", f"{SITE}/about"]
    root, groups = drawn_tree(urls)
    company = root.children["acme.com"]
    assert set(company.children) == {"candidates", "*"}
    pages = company.children["*"]
    assert sitemap.label(pages, {}, "Acme") == "Pages 2 to 9" and not pages.children and pages.pages() == 8


def test_a_list_level_groups_all_its_pages_but_keeps_its_sections():
    urls = [f"{SITE}/blog/how-we-ship-every-single-week-{i}" for i in range(12)]
    urls += [f"{SITE}/blog/{t}" for t in ("design-tokens", "hiring", "q-and-a")]
    urls += [f"{SITE}/blog/category/news", f"{SITE}/about"]
    root, groups = drawn_tree(urls)
    blog = root.children["blog"]
    assert set(blog.children) == {"category", "hiring", "*"}       # a single word stays a section's own page
    assert len(blog.children["*"].children) == 14


def test_a_lists_page_numbers_make_their_own_range():
    urls = [f"{SITE}/blog/how-we-ship-every-single-week-{i}" for i in range(12)]
    urls += [f"{SITE}/blog/{i}" for i in range(2, 6)] + [f"{SITE}/blog/category/news"]
    root, groups = drawn_tree(urls)
    blog = root.children["blog"]
    labels = sorted(sitemap.label(k, {}, "Acme") for k in blog.children.values() if k.virtual)
    assert labels == ["How We Ship Every Single Week 0 and 11 others", "Pages 2 to 5"]


def test_long_titles_next_to_short_ones_are_one_family():
    urls = [f"{SITE}/templates/{t}" for t in ("affinity-diagram", "gantt-chart", "user-flow", "org-chart",
                                               "mind-map", "kanban-board", "swot-analysis", "sitemap",
                                               "wireframe", "flowchart", "venn-diagram", "roadmap")]
    urls += [f"{SITE}/templates/how-to-{t}-a-product-roadmap" for t in ("create", "plan", "share", "present",
                                                                         "review", "update", "write", "draw", "sell")]
    root, groups = drawn_tree(urls)
    assert groups == []


def test_the_top_levels_short_plain_pages_are_never_grouped():
    urls = [f"{SITE}/okrs-board-{i}x9Kq2Lm8Zp" for i in range(20)]
    urls += [f"{SITE}/{p}" for p in ("login", "signup", "pricing", "contact-sales")]
    root, groups = drawn_tree(urls)
    assert set(root.children) == {"login", "signup", "pricing", "contact-sales", "*"}


def test_a_whole_level_of_one_pattern_is_left_as_it_is():
    root, groups = drawn_tree([f"{SITE}/changelog/2026-0{m}-0{d}-release" for m in range(1, 4) for d in range(1, 5)])
    assert groups == [] and len(root.children["changelog"].children) == 12


def test_a_collection_with_no_room_for_examples_is_one_node():
    urls = [f"{SITE}/about"] + [f"{SITE}/acme-{i:03d}.com/candidates" for i in range(100)]
    root, groups = drawn_tree(urls)
    total = root.pages()
    sitemap.layout(root, 4)
    group = root.children["*"]
    assert not group.children and sitemap.label(group, {"/*": "Companies"}, "Acme") == "Companies: 100"
    assert drawn_pages(root) == total


def test_collections_can_be_named_and_layout_counts_them():
    urls = [f"{SITE}/about"] + [f"{SITE}/acme-{i:03d}.com/candidates" for i in range(100)]
    root, groups = drawn_tree(urls)
    total = root.pages()
    assert sitemap.label(root.children["*"], {"/*": "Companies"}, "Acme") == "Companies: 100"
    sitemap.layout(root)
    assert drawn_pages(root) == total and len(root.children["*"].children) == 31


def test_section_is_drawn_on_its_own():
    root = sitemap.section(tree(acme(blog=5, docs=(3,))), "/docs")
    assert root.parent is None and root.path == "/docs"
    assert [n.path for n in root.walk()][:2] == ["/docs", "/docs/section-0"]
    with pytest.raises(sitemap.SitemapError, match="no section /nope"):
        sitemap.section(tree(acme()), "/nope")


# ---------------------------------------------------------------- labels and output

@pytest.mark.parametrize("segment,text", [
    ("data-center", "Data Center"),
    ("robotics-and-edge-ai", "Robotics and Edge AI"),
    ("the-state-of-hr", "The State of HR"),
    ("pt-BR", "Pt BR"),
    ("café-crème", "Café Crème"),
    ("faq_2024", "FAQ 2024"),
    ("acme-labs.com", "acme-labs.com"),
    ("quarterly-okrs-5pegpQuUnnsmRsoEYiaWxh", "Quarterly OKRs"),
    ("9wGACHG5ohHXHVpyEN9hjB", "9wGACHG5ohHXHVpyEN9hjB"),
    ("a" * 90, "A" + "a" * 59 + "..."),
])
def test_label_from_url(segment, text):
    assert sitemap.label_from(segment) == text


def test_labels_drop_what_mermaid_or_markdown_would_misread():
    assert sitemap.clean('Total (EUR) {draft} "new" 100% *star* `x` $5') == "Total EUR draft new 100 star x 5"
    assert sitemap.clean("()") == "Page"


def test_word_fixes_apply_to_every_label():
    words = {"acme cloud": "Acme Cloud", "acmepay": "AcmePay"}
    assert sitemap.label_from("try-acmepay-today", words) == "Try AcmePay Today"
    assert sitemap.label_from("acme-cloud-pricing", words) == "Acme Cloud Pricing"
    assert sitemap.label_from("acmepayments", words) == "Acmepayments"


def test_mindmap_text():
    root = tree(acme(blog=3))
    text = sitemap.mindmap(root, {"/": "Acme"}, "Acme")
    assert text.splitlines() == ["Acme", "- Blog", "  - Post 0000", "  - Post 0001", "  - Post 0002",
                                 "- About", "- Pricing"]
    linked = sitemap.mindmap(root, {}, "Acme", "https://www.acme.com/", "logo-acme")
    assert linked.splitlines()[0] == "[Acme](https://www.acme.com/) icon-name:logo-acme"


def test_root_link():
    meta = {"site": SITE}
    assert sitemap.root_link(meta, tree(acme()), None) == f"{SITE}/"
    no_home = tree([f"{SITE}/en-us/a", f"{SITE}/de-de/a", f"{SITE}/fr-fr/a"])
    assert sitemap.root_link(meta, no_home, "en-us") == f"{SITE}/en-us"
    docs = sitemap.section(tree(acme(docs=(2,))), "/docs")
    assert sitemap.root_link(meta, docs, None) == f"{SITE}/docs"
    odd = tree([f"{SITE}/a (b)", f"{SITE}/c"])
    assert sitemap.root_link(meta, sitemap.section(odd, "/a (b)"), None) == f"{SITE}/a%20%28b%29"


def test_flowchart_text_is_a_class_diagram():
    root = tree(acme(blog=3, docs=(2,)))
    text = sitemap.flowchart(root, {}, "Acme")
    lines = text.splitlines()
    assert lines[:2] == ["classDiagram", "  direction TB"]
    assert '  class n0["Acme"] {' in lines and "    About" in lines
    assert '  class n1["Blog"] {' in lines and "    Post 0000" in lines
    assert sorted(line.strip() for line in lines if "-->" in line) == ["n0 --> n1", "n0 --> n2", "n2 --> n3"]
    for line in lines[2:]:
        assert not re.search(r"[(){}*$%\"]", line.replace(' {', '').replace('["', '').replace('"]', '')) \
            or line.strip() in ("}",), line


def test_sides_balance_the_rows_and_take_the_fewest_moves():
    root = tree(acme(blog=50, docs=(10, 10, 10)))
    branches = sitemap.ordered(root, {}, "Acme")
    left = sitemap.left_branches(root, {}, "Acme")
    assert [branches[i - 1].path for i in left] == ["/blog"]


def test_numbered_pages_sort_as_numbers():
    root = tree([f"{SITE}/jobs/{i}" for i in (10, 2, 1, 21)] + [f"{SITE}/jobs/apply"])
    jobs = root.children["jobs"]
    assert [n.segment for n in sitemap.ordered(jobs, {}, "Acme")] == ["1", "2", "10", "21", "apply"]


def test_crowded_lists_start_collapsed_and_sections_stay_open():
    urls = [f"{SITE}/blog/post-{i:02d}" for i in range(12)]
    urls += [f"{SITE}/docs/{name}/{p}" for name in ("api", "cli", "sdk") for p in range(10)]
    urls += [f"{SITE}/company/{p}" for p in ("careers", "contact", "press")]
    root = tree(urls)
    sitemap.layout(root)
    lines = sitemap.mindmap(root, {}, "Acme").splitlines()
    shut = sitemap.collapsed_lines(root, {}, "Acme", 8)
    names = [lines[n - 1].strip("- ") for n in shut]
    assert names == ["API", "Cli", "SDK", "Blog"]
    assert "Docs" not in names and "Company" not in names and "Acme" not in names
    assert sitemap.collapsed_lines(root, {}, "Acme", 0) == []


def test_collapsed_lines_are_the_mind_maps_line_numbers():
    root = tree(acme(blog=20, docs=(12,)))
    sitemap.layout(root)
    lines = sitemap.mindmap(root, {}, "Acme").splitlines()
    for n in sitemap.collapsed_lines(root, {}, "Acme", 8):
        node = [nd for nd, _ in sitemap.outline(root, {}, "Acme")][n - 1]
        assert lines[n - 1].strip().lstrip("- ") == sitemap.label(node, {}, "Acme")


def test_a_collapsed_list_counts_as_one_row_for_the_sides():
    root = tree(acme(blog=30, docs=(5, 5, 5, 5)))
    sitemap.layout(root)
    assert sitemap.left_branches(root, {}, "Acme") != sitemap.left_branches(root, {}, "Acme", 8)


def test_ranges():
    assert sitemap.ranges([1, 2, 3, 5, 7, 8]) == "1 to 3, 5, 7, 8"
    assert sitemap.ranges([4]) == "4"


def test_labels_file(tmp_path):
    (tmp_path / "labels.json").write_text(json.dumps({"/": "Acme", "/Docs/": "Guides", "acmepay": "AcmePay"}))
    labels = sitemap.read_labels(tmp_path)
    assert labels == {"acmepay": "AcmePay", "/": "Acme", "/docs": "Guides"}
    (tmp_path / "labels.json").write_text('["no"]')
    with pytest.raises(sitemap.SitemapError, match="must map paths or words"):
        sitemap.read_labels(tmp_path)


# ---------------------------------------------------------------- commands

def saved_site(tmp_path, urls):
    folder = tmp_path / "sitemaps" / "acme.com"
    report = {"site": SITE, "domain": "acme.com", "fetched": "2026-11-25", "fetched_at": "2026-11-25T09:30+01:00",
              "pages": urls, "errors": [],
              "off_site": [], "sitemaps": [{"url": f"{SITE}/sitemap.xml", "kind": "pages", "entries": len(urls)}]}
    sitemap.save(report, folder)
    return folder


def test_fetch_reuses_saved_pages(tmp_path):
    saved_site(tmp_path, acme(blog=5))
    out = run_script("fetch", "https://www.acme.com", cwd=tmp_path).stdout
    assert out.startswith("Already fetched on 2026-11-25")
    assert "acme.com: 9 URLs in 1 sitemap file." in out


def test_draw_writes_both_diagrams(tmp_path):
    folder = saved_site(tmp_path, acme(blog=1500))
    (folder / "labels.json").write_text(json.dumps({"/": "Acme", "/nope": "Nope"}))
    out = run_script("draw", folder, "--type", "both", cwd=tmp_path).stdout
    assert (folder / "mindmap.md").read_text().startswith("[Acme](https://www.acme.com/)\n- Blog\n")
    assert (folder / "flowchart.mmd").read_text().startswith("classDiagram\n")
    assert "1,504 pages, 34 of them drawn, in 35 nodes (limit 1,000)." in out
    assert "  - and 1,470 other pages\n" in (folder / "mindmap.md").read_text()
    assert "warning: labels.json names /nope" in out
    assert "Mind map collapsed: nodes 2 (1 of 35" in out


def test_draw_prints_the_flowchart_root_link(tmp_path):
    folder = saved_site(tmp_path, acme(blog=5))
    out = run_script("draw", folder, "--type", "flowchart", "--icon", "logo-acme", cwd=tmp_path).stdout
    assert ('Flowchart root: set the root table\'s header to {"row": 0, "col": 0, '
            '"text": "[acme.com](https://www.acme.com/)", "icon_name": "logo-acme"}.') in out
    result = run_script("draw", folder, "--type", "flowchart", "--icon", "Logo Acme", cwd=tmp_path, check=False)
    assert result.returncode == 1 and "--icon takes an icon name" in result.stderr


def test_note_names_the_sitemap_it_read(tmp_path):
    folder = saved_site(tmp_path, acme(blog=5))
    run_script("draw", folder, "--type", "mindmap", cwd=tmp_path)
    out = run_script("note", folder, cwd=tmp_path).stdout.splitlines()
    assert out == ["[Sitemap of **acme.com**](https://www.acme.com/sitemap.xml), read on 25 Nov 2026 at 09:30.",
                   "**9** pages, all drawn."]


def test_note_says_how_many_pages_are_drawn(tmp_path):
    folder = saved_site(tmp_path, acme(blog=100))
    run_script("draw", folder, "--type", "mindmap", cwd=tmp_path)
    assert run_script("note", folder, cwd=tmp_path).stdout.splitlines()[1] == \
        "**104** pages, **34** of them drawn."


def test_when():
    assert sitemap.when("2026-11-05T09:30+01:00") == "5 Nov 2026 at 09:30"
    assert sitemap.when("2026-11-05") == "5 Nov 2026"


def test_note_needs_a_draw(tmp_path):
    result = run_script("note", tmp_path, cwd=tmp_path, check=False)
    assert result.returncode == 1 and "run `draw` first" in result.stderr


def test_draw_options_are_checked(tmp_path):
    folder = saved_site(tmp_path, acme(blog=5))
    result = run_script("draw", folder, "--type", "both", "--limit", "1500", cwd=tmp_path, check=False)
    assert result.returncode == 1 and "a flowchart takes at most 1,000 nodes" in result.stderr
    assert run_script("draw", folder, "--type", "mindmap", "--limit", "1500", cwd=tmp_path).returncode == 0
    result = run_script("draw", folder, "--type", "mindmap", "--per-level", "250", cwd=tmp_path, check=False)
    assert result.returncode == 1 and "--per-level must be between 1 and 199" in result.stderr
    out = run_script("draw", folder, "--type", "mindmap", "--per-level", "2", cwd=tmp_path).stdout
    assert "9 pages, 5 of them drawn, in 7 nodes" in out


def test_draw_needs_a_fetch_first(tmp_path):
    result = run_script("draw", tmp_path / "sitemaps" / "acme.com", "--type", "mindmap", cwd=tmp_path, check=False)
    assert result.returncode == 1 and "run `fetch <site>` first" in result.stderr


def test_no_sitemap_exits_with_3(monkeypatch, capsys):
    def none(site):
        raise sitemap.NoSitemap("No sitemap found on acme.com: checked robots.txt.")
    monkeypatch.setattr(sitemap, "fetch_site", none)
    monkeypatch.chdir(capsys and __import__("tempfile").mkdtemp())
    with pytest.raises(SystemExit) as stop:
        sitemap.main(["fetch", "acme.com"])
    assert stop.value.code == 3
    assert "No sitemap found on acme.com" in capsys.readouterr().err


def test_script_runs_on_python_3_9():
    # Users run it with whatever python3 they have; macOS ships 3.9. CI runs a newer Python, so
    # check the syntax against 3.9 here. (tests/repo checks it imports only the standard library.)
    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))
