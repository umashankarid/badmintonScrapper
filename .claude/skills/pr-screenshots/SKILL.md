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

## What to accomplish

1. **Confirm there is a PR.** `gh pr view --json number,baseRefName`. If there
   is none, stop and say so — this skill edits a PR body and has nothing to edit.

2. **Render.** From the repo root:

   ```bash
   .venv/Scripts/python.exe .claude/skills/pr-screenshots/shoot.py \
       --out .pr-shots --base <merge-base with the PR's base branch>
   ```

   It works out which pages changed by diffing `<base>...HEAD`:
   a changed `templates/X.html` maps to that page; a change to
   `static/design-system.css` or `static/devbar.js` maps to **every** page,
   because both are global. Pass `--pages a.html,b.html` to override.

   Every page is shot at **375×812 and 1280×900**. That is not configurable and
   should not become configurable — this project's standing rule is that desktop
   and mobile are decided together, so a screenshot set showing one is worse
   than none.

3. **Look at the PNGs before uploading.** Read a representative few. You are
   checking they rendered — content present, no error page, no half-loaded
   table. The script exits non-zero and names the file if a page threw a
   JavaScript error or a selector never appeared. **If any render failed, stop.
   Do not upload a partial set** — a reviewer who sees eight of eleven screens
   assumes the other three were fine.

4. **Ensure the `pr-screenshots` branch exists.** Once per repo, without ever
   checking it out:

   ```bash
   EMPTY=$(git hash-object -t tree /dev/null)
   COMMIT=$(git commit-tree $EMPTY -m "PR screenshots")
   git push origin $COMMIT:refs/heads/pr-screenshots
   ```

5. **Upload** each PNG to `pr/<pr#>/<name>.png` on that branch via the Contents
   API. Overwriting needs the existing blob's `sha`:

   ```bash
   SHA=$(gh api "repos/$OWNER/$REPO/contents/pr/$PR/$NAME?ref=pr-screenshots" \
         --jq .sha 2>/dev/null)
   gh api -X PUT "repos/$OWNER/$REPO/contents/pr/$PR/$NAME" \
     -f message="Screenshot $NAME for #$PR" \
     -f branch=pr-screenshots \
     -f content="$(base64 -w0 .pr-shots/$NAME)" \
     ${SHA:+-f sha=$SHA}
   ```

6. **Edit the PR body**, replacing everything between the markers rather than
   appending — re-running must update the set, not stack a second copy:

   ```markdown
   <!-- pr-screenshots:start -->
   ## Screenshots

   Rendered from the dev-mode fixtures, so tournament names are seeded and a
   `FAKE` badge marks fixture data. Both viewports for every changed page.

   ### Tournament list
   | Mobile (375) | Desktop (1280) |
   |---|---|
   | <img src="https://github.com/OWNER/REPO/raw/pr-screenshots/pr/N/index-player-mobile.png" width="375"> | <img src="https://github.com/OWNER/REPO/raw/pr-screenshots/pr/N/index-player-desktop.png" width="600"> |
   <!-- pr-screenshots:end -->
   ```

   One `###` section per page, in the order `shoot.py` printed them. Use the
   human title it printed, not the filename. A page with both a player and an
   admin view gets a row each, labelled.

   Read the current body first (`gh pr view --json body`), splice between the
   markers, and write it back with `gh pr edit --body-file`.

7. **Clean up** `.pr-shots/` when done.

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
  the code renders. Say in the PR body that the data is seeded instead.
