"""Publish a markdown test plan as a GitHub issue with clickable checkboxes.

The file stays the source of truth; the issue is generated from it. Re-running
after the plan changes keeps every box the tester already ticked -- boxes are
matched by their section and their first line of text, not by position, so
adding, removing or reordering steps does not lose progress.

Usage:
    python .claude/skills/pr-testplan/publish_plan.py \
        --plan docs/manual-test-plan.md --pr 5

Windows notes are the same as pr-screenshots/publish.py: the body goes through
--body-file because it is far past the ~32 KB command-line cap, that file lives
under the repo because gh cannot see Git Bash's /tmp, MSYS_NO_PATHCONV stops
Git Bash rewriting API paths, and encoding="utf-8" stops cp1252 turning an "ä"
into None.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- pr-testplan: {plan} -->"

# The repo is public. A tailnet hostname is not reachable from outside it, but
# it does not need to be on the internet either.
SCRUB = [
    (re.compile(r"\b[a-z0-9-]+\.[a-z0-9-]+\.ts\.net(:\d+)?", re.I), "your-tailscale-host:3002"),
]


def gh(*args, check=True):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run(["gh", *args], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    if check and r.returncode:
        sys.exit(f"gh {' '.join(args[:3])}... failed: {r.stderr.strip()}")
    return r


def checkbox_key(section, line):
    """Identify a checkbox by its section and first line, so reordering or
    inserting steps does not shift which box is considered ticked."""
    text = re.sub(r"^\s*- \[[ xX]\]\s*", "", line)
    return (section, re.sub(r"\s+", " ", text).strip())


def ticked_keys(body):
    """Every box already ticked in the issue, keyed as above."""
    keys, section = set(), ""
    for line in body.splitlines():
        m = re.match(r"^\s*<summary><b>(.+?)</b></summary>\s*$", line)
        if m:
            section = m.group(1)
            continue
        if re.match(r"^\s*- \[[xX]\]", line):
            keys.add(checkbox_key(section, line))
    return keys


def build_body(plan_text, plan_path, pr, keep_ticked):
    for pattern, repl in SCRUB:
        plan_text = pattern.sub(repl, plan_text)

    lines = plan_text.splitlines()
    # Drop the H1; the issue title carries it.
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    out = [MARKER.format(plan=plan_path), ""]
    if pr:
        out += [f"Manual test pass for #{pr}. Source of truth is "
                f"`{plan_path}`; this issue is generated from it and "
                f"re-generating keeps whatever you have already ticked.", ""]

    section, buf, started = "", [], False

    def flush():
        if not started:
            return
        out.append(f"<details>\n<summary><b>{section}</b></summary>\n")
        while buf and not buf[-1].strip():
            buf.pop()
        out.extend(buf)
        out.append("\n</details>\n")

    for line in lines:
        if line.startswith("## "):
            flush()
            section, buf, started = line[3:].strip(), [], True
            continue
        if not started:
            out.append(line)
            continue
        if re.match(r"^\s*- \[ \]", line) and checkbox_key(section, line) in keep_ticked:
            line = line.replace("- [ ]", "- [x]", 1)
        buf.append(line)
    flush()
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--pr", type=int)
    ap.add_argument("--title")
    args = ap.parse_args()

    plan_path = args.plan.as_posix()
    text = args.plan.read_text(encoding="utf-8")
    title = args.title or next(
        (l[2:].strip() for l in text.splitlines() if l.startswith("# ")),
        f"Test plan — {plan_path}")

    marker = MARKER.format(plan=plan_path)
    existing, keep = None, set()
    found = json.loads(gh("issue", "list", "--state", "all", "--limit", "100",
                          "--json", "number,body").stdout or "[]")
    for issue in found:
        if marker in (issue.get("body") or ""):
            existing = issue["number"]
            keep = ticked_keys(issue["body"])
            break

    body = build_body(text, plan_path, args.pr, keep)
    tmp = args.plan.parent / ".testplan-issue.md"
    tmp.write_text(body, encoding="utf-8")
    try:
        if existing:
            gh("issue", "edit", str(existing), "--body-file", str(tmp))
            print(f"updated issue #{existing} ({len(keep)} ticked boxes preserved)")
            url = json.loads(gh("issue", "view", str(existing), "--json", "url").stdout)["url"]
        else:
            url = gh("issue", "create", "--title", title,
                     "--body-file", str(tmp)).stdout.strip().splitlines()[-1]
            print(f"created issue: {url}")
        print(url)
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
