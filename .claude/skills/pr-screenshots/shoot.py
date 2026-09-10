"""Render screenshots of the pages a branch touched, at both viewports.

Reuses the browser suite's harness rather than building a second one: the app
runs as a real subprocess in dev mode against a throwaway DATA_DIR with the
network closed off, exactly as tests/e2e/conftest.py sets it up. That matters
because these pages are JavaScript -- a static render of the template would
show an empty shell.

Usage:
    python .claude/skills/pr-screenshots/shoot.py --out shots/ [--pages a,b]

With no --pages it works out which pages the branch touched by diffing against
the merge base.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tests.e2e import seed                       # noqa: E402
from tests.e2e.conftest import _run_app_server   # noqa: E402


@dataclass
class Page:
    """One screenshottable page.

    `route` may contain {tournament} -- substituted with the seeded fixture's
    URL-encoded tournament_url. `personas` are dev-bar persona usernames; a
    page with two gets shot twice, because the player and admin views of the
    registration page are different screens wearing the same route.
    """
    title: str
    route: str
    personas: list = field(default_factory=lambda: [None])
    settle: str = None          # optional selector to wait for before shooting


# Keyed by the template filename, because that is what `git diff --name-only`
# gives us. Note tournament_detail.html is served at /tournament-detail.html --
# underscore in the file, hyphen in the route. Getting that wrong yields a 404
# screenshot that looks like a broken page.
PAGES = {
    "login.html": Page("Login", "/login.html"),
    "index.html": Page("Tournament list", "/", ["adam"]),
    "tournament.html": Page(
        "Registration", "/tournament.html?url={tournament}",
        ["adam", "sbf04959"], settle="#tournament-name"),
    "results.html": Page("Past tournaments", "/results.html", ["sbf04959"]),
    "tournament_detail.html": Page(
        "Tournament detail", "/tournament-detail.html?id=DEV-T1"),
    "manage.html": Page("Admin hub", "/manage.html", ["sbf04959"]),
    "manage-tournaments.html": Page(
        "Tournaments", "/manage-tournaments.html", ["sbf04959"]),
    "add-remove-tournaments.html": Page(
        "Tournament visibility", "/add-remove-tournaments.html", ["sbf04959"]),
    "manage-admins.html": Page("Admins", "/manage-admins.html", ["sbf04959"]),
    "manage-komet-players.html": Page(
        "Komet players", "/manage-komet-players.html", ["sbf04959"]),
    "manage-db.html": Page("Database", "/manage-db.html", ["sbf04959"]),
    "email-settings.html": Page("Email settings", "/email-settings.html", ["sbf04959"]),
    "send-email.html": Page("Send email", "/send-email.html", ["sbf04959"]),
    # admin.html is a redirect stub that is on screen for a few milliseconds.
    # Deliberately not shot.
}

# Touching either of these changes every page, so shoot the lot.
GLOBAL_FILES = {"static/design-system.css", "static/devbar.js"}

VIEWPORTS = {"mobile": (375, 812), "desktop": (1280, 900)}

PERSONA_LABEL = {"adam": "player", "sbf04959": "admin", None: None}


def changed_pages(base):
    """Map the branch's changed files onto page keys."""
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()

    if any(f in GLOBAL_FILES for f in out):
        return list(PAGES)

    hit = []
    for f in out:
        name = Path(f).name
        if f.startswith("templates/") and name in PAGES:
            hit.append(name)
    return hit


def slug(page_key, persona, viewport):
    stem = page_key.replace(".html", "").replace("_", "-")
    label = PERSONA_LABEL.get(persona)
    return f"{stem}{'-' + label if label else ''}-{viewport}.png"


def sign_in(page, base, persona):
    """Sign in through the dev bar's persona picker.

    devbar.js does `window.location.href = "/"` on success, so arm the
    navigation before selecting -- checking the URL afterwards resolves
    instantly against the page we are already on and races the reload.
    """
    page.goto(f"{base}/")
    page.wait_for_selector("#devbar select")
    with page.expect_navigation(url=f"{base}/"):
        page.locator("#devbar select").select_option(persona)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--base", default=None,
                    help="commit to diff against; default = merge-base with the PR target")
    ap.add_argument("--pages", default=None,
                    help="comma-separated page keys, overriding diff detection")
    args = ap.parse_args()

    if args.pages:
        keys = [k.strip() for k in args.pages.split(",")]
    else:
        keys = changed_pages(args.base or "origin/main")
    keys = [k for k in keys if k in PAGES]

    if not keys:
        print("no UI pages changed; nothing to shoot")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)

    import tempfile
    from playwright.sync_api import sync_playwright

    data_dir = Path(tempfile.mkdtemp(prefix="pr-shots-"))
    server = _run_app_server(data_dir)
    base_url = next(server)

    # Fixtures, so the pages have something in them. An empty table screenshots
    # as an empty table and tells a reviewer nothing.
    open_name = seed.open_tournament(
        data_dir, name="Kometslaget 2026", groups=["SENIOR"])
    seed.past_tournament(data_dir, name="Scandic Cup 2025")
    seed.player(data_dir, "DEV-0001", "Adam Adult")
    seed.registration(data_dir, open_name, "DEV-0001", singles="HS A")
    tournament_url = seed.tournament_url(open_name)

    written, failures = [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for key in keys:
                spec = PAGES[key]
                for persona in spec.personas:
                    for vp_name, (w, h) in VIEWPORTS.items():
                        ctx = browser.new_context(viewport={"width": w, "height": h})
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        try:
                            if persona:
                                sign_in(page, base_url, persona)
                            page.goto(base_url + spec.route.format(
                                tournament=tournament_url))
                            page.wait_for_load_state("networkidle")
                            if spec.settle:
                                page.wait_for_selector(spec.settle, timeout=10000)
                            # The dev bar is a sticky overlay that only ever
                            # exists when DEV_TOOLS is on. It occludes the top
                            # of every shot and is not the UI under review.
                            page.add_style_tag(content="#devbar{display:none!important}")
                            name = slug(key, persona, vp_name)
                            page.screenshot(path=str(args.out / name), full_page=True)
                            written.append((key, spec.title, persona, vp_name, name))
                            if errors:
                                failures.append(f"{name}: page errors {errors}")
                        except Exception as exc:
                            failures.append(f"{slug(key, persona, vp_name)}: {exc}")
                        finally:
                            ctx.close()
            browser.close()
    finally:
        for _ in server:      # drain the generator so it tears the server down
            pass

    for key, title, persona, vp, name in written:
        who = PERSONA_LABEL.get(persona)
        print(f"OK  {name}\t{title}{' (' + who + ')' if who else ''}\t{vp}")

    if failures:
        print("\nFAILURES -- do not upload a partial set:", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
