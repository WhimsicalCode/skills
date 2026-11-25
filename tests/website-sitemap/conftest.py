import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "website-sitemap" / "scripts"
SCRIPT = SCRIPTS / "sitemap.py"
sys.path.insert(0, str(SCRIPTS))

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*urls):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset {NS}>'
            + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>").encode()


def index(*urls):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex {NS}>'
            + "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls) + "</sitemapindex>").encode()


def fake_web(files):
    """A stand-in for http_get: serves `files` by URL and fails like the real one for anything else."""
    import sitemap

    def get(url):
        if url not in files:
            raise sitemap.SitemapError(f"{url}: HTTP 404")
        return files[url]
    return get


def run_script(*args, cwd, check=True):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd, capture_output=True,
                          text=True, check=check)
