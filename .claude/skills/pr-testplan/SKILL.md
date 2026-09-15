---
name: pr-testplan
description: Publish a markdown test plan as a GitHub issue with clickable checkboxes, and re-publish it when the plan changes without losing ticked boxes. Trigger when the user asks to put a test plan on GitHub, share it across devices, or update an existing test-plan issue.
---

# PR Test Plan

A manual test pass gets done from whatever device is to hand — a phone in the
sports hall, a Mac, the PC running the server. A markdown file in the repo is
the wrong place to tick boxes from three devices; a GitHub issue is the right
one. Checkboxes are clickable on github.com and in the mobile app, every tick
saves instantly, and there is nothing to sync.

**The file stays the source of truth.** The issue is generated from it. When the
plan changes, re-run the publisher rather than hand-editing the issue — it keeps
every box the tester has already ticked.

## What to accomplish

1. **Write or update the plan** at `docs/manual-test-plan.md` (or another path —
   the publisher takes `--plan`). Structure it as:
   - an `# H1` — becomes the issue title;
   - a short preamble before the first `## ` — stays at the top of the issue,
     outside any collapsed section;
   - one `## ` per scenario — each becomes a collapsed `<details>` block;
   - `- [ ]` for every check, one observable result per box.

2. **Publish:**

   ```bash
   .venv/Scripts/python.exe .claude/skills/pr-testplan/publish_plan.py \
       --plan docs/manual-test-plan.md --pr <number>
   ```

   First run creates the issue and prints its URL. Later runs find it by the
   `<!-- pr-testplan: <path> -->` marker in its body and edit it in place,
   reporting how many ticks it carried over. Naming the PR puts a
   cross-reference in that PR's timeline without touching its body — which
   matters, because `pr-screenshots` rewrites the PR body and the two would
   fight.

3. **Report the URL to the user** and leave the issue open until the pass is
   done.

4. **Reading progress back:** `gh issue view <n> --json body` and count
   `- [x]`. Useful when the user asks what is left, or before marking a PR
   ready for review.

## How ticks survive a plan change

A box is identified by **its section heading plus its first line of text**, not
by its position in the file. So inserting a step above a ticked one, reordering
scenarios, or editing a different step all leave the tick where it was. Two
boxes with identical text in *different* sections stay independent.

Rewording a step's first line does lose its tick — correctly, since it is no
longer the same check. If you only meant to fix a typo, expect to re-tick it.

## Constraints

- **Never hand-edit the issue body.** The next publish overwrites it. Change the
  plan file and re-publish.
- **Scrub before publishing.** `SCRUB` in `publish_plan.py` rewrites tailnet
  hostnames (`*.*.ts.net`) to a placeholder, because this repo is public. Add a
  pattern there rather than editing the plan to be vaguer — the local file
  should keep the real hostname so it is useful to the person testing.
- The plan file is committed; the generated issue body is not written to disk
  (a temporary `.testplan-issue.md` is removed on the way out).
- Windows: the body is far past the ~32 KB command-line cap, so it goes through
  `--body-file` from a repo-relative path, with `MSYS_NO_PATHCONV=1` and
  `encoding="utf-8"` on the `gh` wrapper. Same four traps as
  `pr-screenshots/publish.py`; do not replace either with a `-f body=…`
  one-liner.
