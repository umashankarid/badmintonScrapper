---
name: pr-screenshots
description: Screenshot every page a PR changed, at mobile and desktop, and embed them in the PR description. Trigger when the user asks to attach / embed / show screenshots or previews on a PR.
---

# PR Screenshots

Render the pages this branch touched at both viewports and embed them in the PR
body. Images live on an orphan `pr-screenshots` branch of this repo, so who can
see them is just who can see the repo.

The templates are JavaScript-driven — a page fetches `/api/*` and builds its own
markup — so a static render shows an empty shell. Screenshots come from the real
app running in a real browser, using the same harness the browser suite uses:
`tests/e2e/conftest.py`'s subprocess server, dev mode, a throwaway `DATA_DIR`,
and the network pointed at a dead proxy.

Two scripts, both run with the project venv — system `python` has no pytest and
`shoot.py` imports the test harness:

- `shoot.py` — decides which pages changed and renders them.
- `publish.py` — uploads the PNGs and rewrites the PR body.

## What to accomplish

1. **Confirm there is a PR.** `gh pr view --json number,baseRefName`. If there
   is none, stop and say so — this skill edits a PR body and has nothing to edit.

2. **Render.** From the repo root:

   ```bash
   .venv/Scripts/python.exe .claude/skills/pr-screenshots/shoot.py \
       --out .pr-shots --base "$(git merge-base origin/<baseRefName> HEAD)"
   ```

   It works out which pages changed by diffing `<base>...HEAD`:
   a changed `templates/X.html` maps to that page; a change to
   `static/design-system.css` or `static/devbar.js` maps to **every** page,
   because both are global. Pass `--pages a.html,b.html` to override.

   Every page is shot at **375×812 and 1280×900**. That is not configurable and
   should not become configurable — this project's standing rule is that desktop
   and mobile are decided together, so a screenshot set showing one is worse
   than none. A full run of all 13 pages takes about four minutes.

3. **Look at the PNGs before uploading.** Read a representative few. You are
   checking they rendered — content present, no error page, no half-loaded
   table. The script exits non-zero and names the file if a page threw a
   JavaScript error or a selector never appeared. **If any render failed, stop.
   Do not upload a partial set** — a reviewer who sees eight of eleven screens
   assumes the other three were fine.

4. **Publish.**

   ```bash
   .venv/Scripts/python.exe .claude/skills/pr-screenshots/publish.py \
       --shots .pr-shots --pr <number>
   ```

   This creates the `pr-screenshots` branch if it is missing (from the empty
   tree, by hash — it is never checked out), uploads each PNG to
   `pr/<pr#>/<name>.png` via the Contents API passing the existing blob `sha`
   when overwriting, and rewrites the PR body between
   `<!-- pr-screenshots:start -->` / `<!-- pr-screenshots:end -->`. Re-runs
   replace that block; they never append a second one. A body with no markers
   gets the block inserted above the "Generated with" trailer.

   The section is one `###` per page in `shoot.py`'s order, a two-column table
   of mobile and desktop, and a labelled row per persona on pages that are shot
   as both player and admin.

5. **Verify** — `gh pr view <n> --json body --jq .body | grep -c pr-screenshots:`
   must print `2`, and
   `gh api "repos/<owner>/<repo>/contents/pr/<n>?ref=pr-screenshots" --jq length`
   must match the number of PNGs. Then `rm -rf .pr-shots`.

## Why publish.py exists

The obvious one-liner, `gh api -X PUT ... -f content="$(base64 -w0 file)"`,
fails on Windows three separate ways, and each failure is silent enough to look
like an auth problem:

- a base64 PNG is ~50 KB and Windows caps a command line at ~32 KB, so `-f`
  cannot carry it — the body must go through `--input <file>`;
- `gh` is a Windows binary and cannot see Git Bash's `/tmp`, so that file must
  live under the repo;
- Git Bash rewrites arguments that look like paths (`repos/owner/...`) into
  filesystem paths unless `MSYS_NO_PATHCONV=1` is set;
- Python's `subprocess.run(text=True)` decodes with the console codepage,
  cp1252 on Windows — a PR body containing an emoji or an `ä` raises inside
  the reader thread and `.stdout` silently comes back `None`. The wrapper
  forces `encoding="utf-8"`.

`publish.py` handles all four. Do not replace it with the one-liner.

## Adding a page

`PAGES` in `shoot.py` maps a template filename to its route, the dev-bar
personas to shoot it as, and an optional selector to wait for. Two traps:

- `tournament_detail.html` is served at `/tournament-detail.html` — underscore
  in the file, hyphen in the route. Getting it wrong yields a 404 that
  screenshots as a plausible-looking broken page.
- `admin.html` is deliberately absent. It is a redirect stub visible for a few
  milliseconds.

Pages that need data need it seeded in `main()` — an empty table screenshots as
an empty table and tells a reviewer nothing. The fixtures there today are one
open tournament, one past tournament, one Komet player and one registration.

## Constraints

- **Never check out `pr-screenshots`, never merge it, never rebase onto it.**
  It is an orphan branch of loose files reached only through the Contents API.
- Abort if there is no PR for the current branch.
- Abort on any failed render rather than uploading what worked.
- The dev bar is hidden before each shot — it is a `DEV_TOOLS`-only overlay that
  covers the top of the page and is not the UI under review. Fixture markers
  like the `FAKE` badge are left alone: doctoring them would misrepresent what
  the code renders. The PR body says the data is seeded instead.
