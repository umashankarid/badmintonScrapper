"""Upload rendered screenshots to the orphan pr-screenshots branch and embed
them in the PR body.

Usage:
    python .claude/skills/pr-screenshots/publish.py --shots .pr-shots --pr 5

Three things this does that a plain `gh api -f content=...` loop cannot, all
learned the hard way on Windows:
  - the JSON body goes through --input from a file, because a base64 PNG is
    ~50 KB and Windows caps a command line at ~32 KB;
  - that file lives under the repo, because `gh` is a Windows binary and cannot
    see Git Bash's /tmp;
  - MSYS_NO_PATHCONV is set so Git Bash does not rewrite `repos/...` API paths
    as filesystem paths.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shoot import PAGES, PERSONA_LABEL, slug   # noqa: E402

START, END = "<!-- pr-screenshots:start -->", "<!-- pr-screenshots:end -->"


def gh(*args, check=True):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    # encoding is explicit because text=True alone decodes with the console
    # codepage (cp1252 on Windows); a PR body with an emoji or an "ä" then
    # raises inside subprocess's reader thread and .stdout comes back None.
    r = subprocess.run(["gh", *args], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    if check and r.returncode:
        sys.exit(f"gh {' '.join(args[:3])}... failed: {r.stderr.strip()}")
    return r


def repo_slug():
    return gh("repo", "view", "--json", "nameWithOwner",
              "--jq", ".nameWithOwner").stdout.strip()


def ensure_branch(slug_):
    if gh("api", f"repos/{slug_}/branches/pr-screenshots", check=False).returncode == 0:
        return
    # Orphan branch from the empty tree, pushed by hash -- never checked out.
    empty = subprocess.check_output(
        ["git", "hash-object", "-t", "tree", os.devnull], text=True).strip()
    commit = subprocess.check_output(
        ["git", "commit-tree", empty, "-m", "PR screenshots"], text=True).strip()
    subprocess.run(["git", "push", "origin", f"{commit}:refs/heads/pr-screenshots"],
                   check=True)
    print("created orphan branch pr-screenshots")


def upload(slug_, pr, shots):
    body_file = shots / ".put.json"
    names = []
    for f in sorted(shots.glob("*.png")):
        api = f"repos/{slug_}/contents/pr/{pr}/{f.name}"
        sha = gh("api", f"{api}?ref=pr-screenshots", "--jq", ".sha", check=False).stdout.strip()
        body = {"message": f"Screenshot {f.name} for #{pr}", "branch": "pr-screenshots",
                "content": base64.b64encode(f.read_bytes()).decode()}
        if sha:
            body["sha"] = sha
        body_file.write_text(json.dumps(body))
        gh("api", "-X", "PUT", api, "--input", str(body_file))
        names.append(f.name)
    body_file.unlink(missing_ok=True)
    return names


def section(slug_, pr, have):
    raw = f"https://github.com/{slug_}/raw/pr-screenshots/pr/{pr}/"
    lines = [START, "## Screenshots", "",
             "Rendered from the dev-mode fixtures, so tournament names are seeded "
             "and a `FAKE` badge marks fixture data. Both viewports for every "
             "changed page.", ""]
    for key, spec in PAGES.items():
        rows = []
        for persona in spec.personas:
            m, d = slug(key, persona, "mobile"), slug(key, persona, "desktop")
            if m not in have or d not in have:
                continue
            who = PERSONA_LABEL.get(persona)
            label = f"**{who}** " if who and len(spec.personas) > 1 else ""
            rows.append(f'| {label}<img src="{raw}{m}" width="300"> '
                        f'| <img src="{raw}{d}" width="620"> |')
        if rows:
            lines += [f"### {spec.title}", "| Mobile (375) | Desktop (1280) |",
                      "|---|---|", *rows, ""]
    lines.append(END)
    return "\n".join(lines)


def splice(body, new):
    """Replace the marked block, or insert one above the generated-with trailer."""
    if START in body and END in body:
        return body[:body.index(START)] + new + body[body.index(END) + len(END):]
    i = body.rfind("🤖 Generated with")
    if i >= 0:
        return body[:i].rstrip() + "\n\n" + new + "\n\n" + body[i:]
    return body.rstrip() + "\n\n" + new + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True, type=Path)
    ap.add_argument("--pr", required=True, type=int)
    args = ap.parse_args()

    slug_ = repo_slug()
    ensure_branch(slug_)
    names = upload(slug_, args.pr, args.shots)
    print(f"uploaded {len(names)} to pr/{args.pr}/ on pr-screenshots")

    body = json.loads(gh("pr", "view", str(args.pr), "--json", "body").stdout)["body"]
    new_body = splice(body, section(slug_, args.pr, set(names)))
    body_file = args.shots / ".body.md"
    body_file.write_text(new_body, encoding="utf-8")
    gh("pr", "edit", str(args.pr), "--body-file", str(body_file))
    body_file.unlink()
    print(f"PR #{args.pr} body updated")


if __name__ == "__main__":
    main()
