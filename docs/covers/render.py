# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.48,<2"]
# ///
"""Render each skill's cover, docs/covers/<name>.png, from template.html, <name>.json and art/<name>.svg.

    uv run docs/covers/render.py                  # every cover
    uv run docs/covers/render.py app-wireframe    # one cover

The first time, install the browser it renders with:

    uv run --with playwright playwright install chromium
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

COVERS = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 1600, 1000, 2

FILL = """({ spec, art }) => {
  for (const el of document.querySelectorAll("[data-field]")) el.textContent = spec[el.dataset.field]
  document.querySelector("[data-art]").innerHTML = art
}"""


def load(name):
    spec_path, art_path = COVERS / f"{name}.json", COVERS / "art" / f"{name}.svg"
    for path in (spec_path, art_path):
        if not path.is_file():
            sys.exit(f"Missing {path.relative_to(COVERS.parents[1])}: see docs/covers/README.md")
    spec = json.loads(spec_path.read_text())
    return {**spec, "slug": f"/{name}"}, art_path.read_text()


def main():
    names = sys.argv[1:] or sorted(p.stem for p in COVERS.glob("*.json"))
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error as error:
            if "Executable doesn't exist" in str(error):
                sys.exit("Chromium isn't installed. Run: uv run --with playwright playwright install chromium")
            raise
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=SCALE)
        for name in names:
            spec, art = load(name)
            page.goto((COVERS / "template.html").as_uri())
            page.evaluate(FILL, {"spec": spec, "art": art})
            page.evaluate("document.fonts.ready")
            # The fonts come from github.com/WhimsicalCode/fonts; don't save a cover in a fallback font.
            if not page.evaluate("['700 10px Dinsical', '10px Monsical'].every(f => document.fonts.check(f))"):
                sys.exit("Couldn't load Dinsical and Monsical from github.com/WhimsicalCode/fonts")
            page.screenshot(path=COVERS / f"{name}.png")
            print(f"docs/covers/{name}.png")
        browser.close()


if __name__ == "__main__":
    main()
