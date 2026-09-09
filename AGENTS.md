# AGENTS.md

Guidance for AI coding agents working in this repository. This is the single source of truth; `CLAUDE.md` and any other agent-specific file should point here rather than duplicate it.

## What this is

Tournament registration system for the Swedish badminton club BMK Komet. Flask + SQLite + vanilla-JS pages. It wraps Badminton Sweden (`badmintonsweden.tournamentsoftware.com`, "BWF" in the code): players log in with their real BWF credentials, register for tournaments locally, and an admin later bulk-submits all registrations back to BWF. Emails go out via the Brevo HTTP API.

## Commands

```bash
pip install -r requirements.txt
python app.py                                  # serves on http://localhost:3000

python3 run_tests.py                           # the gate used by build.sh (runs test_badminton.py only)
python3 -m unittest test_badminton -v
python3 -m unittest test_badminton.TestTournamentVisibility.test_toggle_tournament_visibility -v
python3 -m pytest test_player_storage.py -v    # other test_*.py are run individually

pytest -m "not live" --ignore=tests/e2e         # the offline suite, what CI gates on
pytest tests/e2e                                # the browser suite (needs: playwright install chromium)
pytest -m live                                  # reaches the real site; needs credentials, never runs in CI
```

`app.py` runs `test_badminton.py` at import time and calls `sys.exit(1)` if anything fails — a broken test in that one file stops the server from booting. `build.sh` (Render/Coolify build step) runs the same gate.

Not all `test_*.py` files are unit tests: `test_bwf_steps.py`, `test_bwf_doubles.py`, and `test_live_ensure_tournament.py` hit the live Badminton Sweden site (Playwright/HTTP) and need real credentials. Don't add them to `unittest discover` runs. They also carry pytest's `@pytest.mark.live` (declared in `pytest.ini`), so a plain `pytest` run deselects them with `-m "not live"`; CI always runs with that flag and never sets credentials. `test_ensure_tournament_e2e.py` is misleadingly named despite the "e2e": it never touches the network or `app.py` -- it builds its own temp SQLite file with hardcoded tournament data and asserts against that. It carries no `live` marker because it doesn't need one, and runs as part of the ordinary offline suite in CI.

**The browser suite** (`tests/e2e/`) boots `app.py` as a subprocess in dev mode with its own temporary `DATA_DIR` and outbound HTTP blocked, then drives Chromium against it via Playwright/pytest-playwright. State is seeded by writing SQLite directly, and every write lives in `tests/e2e/seed.py` — put new state builders there rather than inline in a test, so a schema change breaks one file instead of many. CI runs it as a separate job from the offline suite (`.github/workflows/ci.yml`) because it needs `playwright install --with-deps chromium` first.

Docker: `python:3.10-slim` + Playwright Chromium, `CMD python app.py`, port 3000.

## Architecture

**`app.py` (~6100 lines) is the whole server.** Every route, every DB helper, all email logic. It is organized by `# ---` / `# ====` section banners (Static pages, BWF login, Tournament CRUD, Players in tournament, Results, Database backup, Database viewer). Put new code in the matching section rather than starting a new module — the supporting modules exist only for work that doesn't belong inline:

- `players_scraper.py` — scrapes a player profile by license ID into `players.db`; also owns the `allplayers` table (background scraper is currently disabled at startup).
- `bwf_submit.py` — Playwright automation that logs into BWF with the club account and files the whole club's entries through the "Online-anmälan som grupp" flow. The Team Manager details are hardcoded.
- `db_viewer.py` — read-only table browsing/export behind `/manage-db.html`.
- `scraper.py` — standalone legacy A–Z player crawler, writes an older `players` schema. Not wired into the app.
- `REFACTORED_ENDPOINTS.py` — reference snippets from an old refactor, not imported.

**Badminton Sweden access goes through one boundary.** `app.py` calls `bwf_client`,
which dispatches every call to `bwf_live` (real scraping) or `bwf_dev` (fixtures and
stubs), depending on the mode. The mode is `"live"` unless `DEV_TOOLS` is set, which
happens only in `run-local.ps1` — production never sets it, so `bwf_client.get_mode()`
always returns `"live"` there. New scraping code belongs in `bwf_live`, with a matching
stub added to `bwf_dev` (`test_dev_mode.py::TestGuards` fails the build if the two drift,
by name or by signature). Known gap: two by-name lookups were never moved behind the
boundary — `_register_partner`'s short-partner-name safeguard and `player_details`'s
`if not profile_url:` branch — so those two still call `tournamentsoftware.com` directly
and hit the live site even when dev mode is on. A guard test pins that to exactly those
two functions so a third leak would fail the build.

**Four SQLite databases**, all under `DATA_DIR` (env var, defaults to the repo dir; set to a persistent volume in production):

| DB | Holds |
|----|----|
| `tournaments.db` | `tournaments` (PK is `tournament_name`), `tournament_registrations`, `reminder_opt_out` |
| `players.db` | `players` (keyed by `license_id`), `kometPlayers`, `player_groups`, `allplayers` |
| `admin.db` | `admin_users`, `smtp_settings`, `reminders_sent`, `email_events` |
| `point_rules.db` | `point_rules` — min/max ranking points per level (Elit/A/B/C/D) per category |

**Schema changes are done in place.** `init_tournaments_db()` / `init_admin_db()` / `init_players_db()` run at module import and use `CREATE TABLE IF NOT EXISTS` plus a stack of `try: ALTER TABLE ... ADD COLUMN / except: pass`. Add new columns the same way — there is no migration framework, and the `migrate_*.py` scripts are one-off historical tools. Cross-DB queries use `ATTACH DATABASE`.

**Templates are static files, not Jinja.** They are served with `send_from_directory("templates", ...)`, so `{{ }}` will not render. Each page is one HTML file with an inline `<script>` calling `/api/*` with `fetch`; `templates/tournament.html` (~2000 lines) is the main registration UI. No build step, no framework, no bundler. A new page = new file in `templates/` + a route in the "Static pages" block.

**Auth is session-based and proxied to BWF.** `/api/bwf-login` posts the user's credentials to tournamentsoftware.com, parses the response with BeautifulSoup, and caches the player's name/license/club/ranking in the Flask session. `session["admin"]` is set when the username exists in `admin_users` (club accounts have no player profile and are special-cased by username). Admin endpoints guard with `if not session.get("admin"): return jsonify(success=False, error="Unauthorized"), 401`.

**Email.** `send_email()` posts to `https://api.brevo.com/v3/smtp/email`. Despite the table name, `smtp_settings.smtp_password` stores the **Brevo API key** and `smtp_host`/`smtp_port` are unused. Bounces/blocks arrive on `/api/brevo-webhook` and land in `email_events`.

**Reminder scheduler.** A daemon thread started only under `if __name__ == "__main__"` runs `send_reminders()` every 30 minutes. It sends four kinds of mail — registration deadline at 3 and 0 days (`{days_left}days`), competition start at 3 and 0 days (`comp_{n}days`), cancellation deadline at 1 day (`cancel_1day`), plus an admin notification the day *after* registration closes. Deduplication is by writing `reminders_sent.tournament_db = f"{tournament_name}_{reminder_type}"` with the recipient email and date; `/api/reset-reminder` deletes those rows to force a resend.

## Domain rules that are easy to get wrong

Tournament events are strings like `"HS A"`, `"DD B"`, `"MD Elit"`, `"HS U15"` — category (HS/DS/HD/DD/MD) plus level. Levels are either adult classes (Elit, A, B, C, D) or age classes (U9…U19).

- **Swedish age-group rule**: a player stays in U*X* while `check_year < birth_year + X`, or in the transition year itself if the month is ≤ 6. They move up from July of the year they turn X. Validation is against the tournament's `competition_start`, not today. See `validate_registration()`.
- Under 18 is hard-blocked from C and D (senior-only). Under 13 in any senior class is a soft block requiring dispens — the frontend shows a confirmation popup.
- Ranking points are checked against `point_rules`: above `max` is a hard block, below `min` is a soft warning. `_check_points_too_high()` re-checks this server-side on `/api/add-player`.
- **MJT/SJT**: only for tournaments with "SJT" in the name. A player's training level comes from `kometPlayers.groups`; `"LEVEL 3-5"` is one group name (not three) and those players may only enter MJT events, while `LEVEL_6` may enter both.
- `tournaments.tournament_groups` (JSON list) gates who sees a tournament at all — it is intersected with the player's `kometPlayers.groups`, and also filters reminder recipients.
- Doubles/mixed partners are stored as free-text names in `doubles_partner`/`mixed_partner`, and registering one player auto-creates a registration row for the partner (`_register_partner`) and emails them. Removing a pairing has to unwind the partner's row too (`_cleanup_removed_partner`).

User-facing error messages are bilingual: Swedish first, blank line, then English. Keep that pattern.

## Repo conventions

`CODE_GUIDELINES.md` is the active working agreement and its rules apply here: write the test first, log every operation (INFO for events, ERROR for failures, the codebase uses ✅/❌/📧 emoji prefixes consistently), update `CHANGES.md` with every commit, and **never push without explicit user approval**.

**Do not commit plans or specs.** Design documents, implementation plans, task breakdowns and similar planning artifacts stay local — `docs/superpowers/` is gitignored for this reason. They are working notes for a single piece of work, they go stale the moment the code moves on, and this repository already carries a dozen abandoned `*_PLAN.md` and `*_SUMMARY.md` files that prove the point. Put the reasoning that outlives the task in the commit message, in `CHANGES.md`, or here.

Most other root-level `.md` files (`FINAL_STATUS.md`, `SESSION_SUMMARY.md`, `PHASE_5_COMPLETE.md`, `PROGRESS_SUMMARY.md`, `*_PLAN.md`, …) are historical session logs from past refactors and are stale — `ACTUAL_DB_STRUCTURE.md` in particular still claims `tournaments.db` doesn't exist and that per-tournament `.db` files are in use. That migration is done: registrations live in `tournaments.db`, and `get_tournament_db()` is a deprecated stub that returns `None`. Read those files as history, not as spec.
