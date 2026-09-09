# Local development mode — design

**Date**: 2026-09-09
**Status**: Design approved, not yet implemented
**Scope**: Let the whole application run on a developer machine with no real Badminton Sweden credentials and no live external calls, behind a live/dev switch that only exists locally.

---

## Problem

Every meaningful flow in this application depends on a live third party. Logging in posts real credentials to `badmintonsweden.tournamentsoftware.com` and reads the response; player search, ranking points, tournament dates, event categories and results are all scraped from that same site; registrations are filed back to it through Playwright. Email goes out through the Brevo API.

The consequences for local development are:

- You cannot log in, and therefore cannot reach any page, without real credentials for a real person.
- Testing the registration rules — age groups, junior class restrictions, points minimums and maximums, MJT/SJT levels — means finding real players whose real data happens to hit the case you want to exercise.
- Development is impossible offline and slow when online, because every page load waits on scraping.
- The one write path files real tournament entries. It is protected only by the fact that a human must type the club password.

`EMAIL_ENABLED=0` already solved this for outbound email. This design does the equivalent for Badminton Sweden.

---

## Decisions taken

These were settled during brainstorming and constrain everything below.

| Question | Decision |
| --- | --- |
| How faithful should the fake be? | **Function-level stubs.** No recorded HTML, no hand-written fixtures. The stub returns the same Python structures the real scraper returns. |
| How is the switch controlled? | **Runtime toggle in the UI, plus a persistent banner.** Flipping takes effect without a restart. |
| What is the default? | **Live.** A freshly started local server talks to the real site until someone switches it. |
| What must work in dev mode? | **All four read flows**: login, player search/details/ranking, tournament discovery/info, results pages. |
| What does the write path do? | **Simulates success.** Playwright is never launched in dev mode; the endpoint returns the shape the real submitter returns. |
| Where does the branch live? | **A `bwf_client.py` boundary.** All Badminton Sweden access moves out of `app.py`. |

### Accepted trade-off

Function-level stubs mean the scraping and parsing code does not run in dev mode. A selector change on the Badminton Sweden site will still only be discovered in production. Dev mode makes the *registration and domain logic* testable offline; it does not make the *scraping* testable offline. This is a deliberate choice of cheapness over fidelity, recorded here so nobody later mistakes it for an oversight.

### Known sharp edge

Because live is the default, a local server will hit the real site until it is switched. This is harmless for reads, and the write path requires a typed password, but it means "I started the server and logged in" is a real network call by default.

---

## Architecture

### Mode resolution

Two independent concepts, deliberately not conflated.

**`DEV_TOOLS`** is an environment variable set only in `run-local.ps1`. It answers "may this server offer a dev mode at all?". Production never sets it. When it is unset the toggle endpoint does not exist, the banner never renders, and no stub code is reachable.

**The current mode** is a process-level global, `"live"` or `"dev"`, initialised to `"live"` on every boot. It is not persisted, so a restart always returns to live. It is read per request rather than at import time, which is what allows the toggle to work without a restart.

```
DEV_TOOLS unset  →  mode is always "live", toggle returns 404          (production)
DEV_TOOLS=1      →  mode starts "live", toggle switches it at runtime  (local)
```

### Endpoints

```
GET  /api/dev-mode   →  {"dev_tools": true, "mode": "live"}
POST /api/dev-mode   →  {"mode": "dev"}  switches; returns the new state
```

Both return `404` when `DEV_TOOLS` is unset — not `403`, so that production does not advertise the existence of a feature it does not have. `POST` requires an admin session, matching every other mutating endpoint in the app.

### Module layout

Three new modules and one shrinking one.

```
app.py          calls bwf_client only; contains no Badminton Sweden URLs
bwf_client.py   the dispatcher: picks live or dev per call, owns mode state
bwf_live.py     today's scraping code, moved verbatim
bwf_dev.py      stubs and fake data
```

The dispatcher is deliberately dull:

```python
def search_players(query):
    return _backend().search_players(query)

def _backend():
    return bwf_dev if get_mode() == "dev" else bwf_live
```

`players_scraper.py` routes its two calls through the same client. `bwf_submit.py` stays as the Playwright implementation, called by `bwf_live.submit_registrations()`; `bwf_dev.submit_registrations()` returns a success structure without importing Playwright at all.

`send_email()` is not part of this. `EMAIL_ENABLED` already covers Brevo and there is no reason to have two mechanisms.

### Client surface

Derived from the sixteen functions in `app.py` that currently reach Badminton Sweden. (A seventeenth, `send_email()`, reaches Brevo instead and is out of scope.)

| Function | Replaces the scraping in |
| --- | --- |
| `login(username, password)` | `bwf_login()` |
| `verify_credentials(username, password)` | `add_admin()`, which authenticates a prospective admin against the site and keeps only the pass/fail |
| `search_players(query)` | `search_players()` |
| `get_player_details(profile_url)` | `player_details()`, `_register_partner()` |
| `get_player_ranking(profile_url)` | `get_player_ranking()` |
| `get_player_license(name)` | `get_player_license()` |
| `search_tournaments(query)` | `search_tournaments()`, `search_tournaments_bwf()` |
| `fetch_tournament_info(url)` | `fetch_tournament_info()`, `ensure_tournament()` |
| `list_all_tournaments(start, end)` | `get_all_bwf_tournaments()` |
| `get_tournament_events(tid)` | `ensure_tournament()` |
| `get_tournament_medals(tid)` | `tournament_medals()` |
| `get_tournament_clubs(tid)` | `tournament_clubs()` |
| `get_tournament_player_id(tid, name)` | `tournament_player_id()` |
| `get_tournament_player_results(tid, pid)` | `tournament_player_results()` |
| `submit_registrations(name, login, password)` | `submit_tournament()` |

Each returns plain Python structures — the shapes `app.py` already builds after parsing — so the live implementations are a move, not a rewrite. Where a route currently parses HTML inline and immediately writes to the database, only the parsing half moves.

---

## Fake data

`bwf_dev.py` holds personas chosen to exercise the domain rules rather than merely to populate a page. Every rule in `AGENTS.md` under "Domain rules that are easy to get wrong" should be reachable without hunting for a real player who happens to fit.

**Players**

| Persona | Exercises |
| --- | --- |
| Club/admin account | Admin login with no player profile, the `sbf04959` code path |
| Adult, A-level points | Normal senior registration, points within range |
| Adult, points above A maximum | The hard block on exceeding a class maximum |
| 15-year-old | U15/U17 age-group boundary, junior blocked from C and D |
| Under-13 | The dispens confirmation path for senior classes |
| Komet player in `LEVEL 3-5` | MJT-only restriction in SJT tournaments |
| Komet player in `LEVEL 6` | Permitted in both MJT and SJT |
| Two spare partners | Doubles and mixed partner registration and cleanup |

**Tournaments**

| Fixture | Exercises |
| --- | --- |
| Open, deadline in the future | The ordinary registration flow |
| Name containing `SJT` | The MJT/SJT level split |
| Past, registration closed | Closed-tournament handling and the admin-only view |
| Accommodation enabled | The accommodation and transport fields |

**All dates are computed relative to today**, never hardcoded. A fixture with a hardcoded 2026 deadline silently becomes a "closed tournament" fixture next year and the open-registration path quietly stops being covered. Relative dates also mean the reminder windows (3 days and 0 days before the deadline, 1 day before cancellation) can be hit on demand by picking the right fixture.

Stub responses carry `"_fake": true`. Nothing in the live path ever sets it.

---

## User interface

The templates are static HTML served by `send_from_directory`, not Jinja, so the bar cannot be injected server-side. A shared `static/devbar.js`, included by each template, fetches `/api/dev-mode` on load:

- `404` or a failed fetch — the script does nothing at all. This is production.
- `mode: "live"` — a green bar reading *LIVE — real Badminton Sweden*, with a switch.
- `mode: "dev"` — an orange bar reading *DEV — fake data, nothing leaves this machine*, with a switch.

Rows rendered from data carrying `_fake` get a small marker, so a stubbed player cannot be mistaken for a real one in a screenshot or a bug report.

The bar is deliberately always present when `DEV_TOOLS` is on, including in live mode. A switch you can only see in one of its two states is a switch you will eventually forget you flipped.

---

## Testing

The extraction rewrites sixteen functions that currently have no tests at all, on the flow that carries tournament registrations. The testing plan is therefore mostly about making that extraction safe, and only secondarily about the new feature.

**Before extracting anything**, characterization tests pin the current behaviour of each function, using `unittest.mock.patch` over `requests` — the pattern already established in `test_player_storage.py` and `test_tournament_scraping.py`. These tests describe what the code does today, correct or not. They are the safety net for the move.

**During extraction**, one function per commit, with the suite green at each step. A commit that moves two functions cannot tell you which one broke.

**After extraction**, three guard tests:

1. **No leakage in source.** No occurrence of `tournamentsoftware.com` survives in `app.py`. A cheap, mechanical check that the boundary is real and stays real.
2. **No leakage at runtime.** In dev mode, with `requests` patched to raise on any call and Playwright unavailable, every flow still completes. This is the actual proof of the feature: not "the stubs return data" but "nothing reaches the network".
3. **Production is unaffected.** With `DEV_TOOLS` unset, `POST /api/dev-mode` returns 404 and `get_mode()` returns `"live"` no matter what is posted.

New tests go in `test_bwf_client.py` and `test_dev_mode.py`. The existing gate, `test_badminton.py`, is left alone — it blocks server startup, so adding slow or elaborate tests to it has a cost on every boot.

---

## What this does not do

- It does not fake the scraping. See the accepted trade-off above.
- It does not seed the local database. Dev mode fakes the *external* site; local tournaments and registrations are still created through the normal admin flow, which now works offline.
- It does not touch `send_email()`, `scraper.py` (a standalone legacy crawler, unused by the app) or the Brevo webhook.

  Brevo is the transactional email provider the app sends through. Folding it into the dev toggle was considered and rejected: `EMAIL_ENABLED=0`, set in `run-local.ps1`, already prevents every send, so there is nothing left to leak and no reason to have two mechanisms doing one job. The option not taken was capturing dev-mode messages into the existing `email_events` table so the existing viewer in `email-settings.html` could show them. What that costs us: message bodies stay invisible except as a log line, so the four reminder templates, the bilingual text and attachment handling still cannot be inspected offline. If that becomes annoying, capture-to-`email_events` is the cheap fix — it needs no new table and no new page.
- It does not persist the chosen mode. Restart returns to live, on purpose.

---

## Production impact

None, by construction:

- `DEV_TOOLS` is unset in production, so the toggle 404s and `get_mode()` is hard-wired to `"live"`.
- The live implementations are moved code, not rewritten code, covered by characterization tests written before the move.
- `Dockerfile`, `EXPOSE 3000` and the deployment path are untouched.
- No database schema changes.
