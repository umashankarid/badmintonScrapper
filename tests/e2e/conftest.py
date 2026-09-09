"""Fixtures for the browser suite.

The app runs as a real subprocess rather than through Flask's test client:
the point of these tests is the JavaScript in the templates, and the test
client never runs any.
"""

import collections
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import shutil
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port():
    """Claim a port, release it, return it. Lets parallel runs coexist."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def data_dir():
    """A throwaway DATA_DIR. Never the developer's real databases."""
    path = Path(tempfile.mkdtemp(prefix="e2e-data-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _run_app_server(data_dir):
    """Boot app.py in dev mode against data_dir with the network closed off,
    yield its base URL, tear the subprocess down on exit.

    A plain generator rather than a fixture itself, so it can back both the
    session-scoped app_server fixture (shared by most of the suite) and a
    function-scoped one for a test that needs its own isolated instance.
    """
    port = _free_port()
    env = dict(os.environ)
    env.update({
        "PORT": str(port),
        "HOST": "127.0.0.1",
        "DEBUG": "0",
        "DATA_DIR": str(data_dir),
        "DEV_TOOLS": "1",
        "EMAIL_ENABLED": "0",
        # Dev mode routes the boundary to stubs, but two lookups were left
        # unextracted and still reach the live site -- and one is reachable
        # from the partner search box. Point outbound HTTP at a closed port so
        # any such call fails instantly and names the URL, instead of making
        # CI depend on a third party.
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost",
    })

    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"

    # Drain the child's output for as long as it lives. Nobody reads it
    # otherwise, and this app logs a line or more per request -- once that
    # crosses the OS pipe buffer (a handful of page loads' worth), the next
    # write blocks the child, and the single-threaded dev server never
    # handles another request for the rest of the run. Keep a short tail so
    # a startup failure can still report why.
    log_tail = collections.deque(maxlen=200)
    drain_thread = threading.Thread(
        target=lambda: [log_tail.append(line) for line in proc.stdout],
        daemon=True,
    )
    drain_thread.start()

    def _log_tail_text():
        """The tail, safe to read only once the process has exited: join the
        drain thread first so it isn't still appending to `log_tail` while we
        read it -- on the one path that must report a real startup failure.
        Once stdout closes the thread's for-loop hits EOF and returns almost
        immediately. join(timeout=5) returns regardless of whether the thread
        actually finished, so snapshot with list() before joining the bytes:
        iterating the deque directly races any append still in flight and
        "deque mutated during iteration" would replace the real error.
        """
        drain_thread.join(timeout=5)
        return b"".join(list(log_tail)).decode(errors="replace")

    def _kill(proc):
        """Best-effort kill for an error path. wait() after kill() can still
        raise TimeoutExpired on a wedged child -- never let that swallow the
        caller's real error."""
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early:\n{_log_tail_text()}")
        try:
            if requests.get(f"{base}/api/dev-mode", timeout=1).ok:
                break
        except requests.RequestException:
            pass
        # Outside the except: a non-2xx response (.ok is False) raises
        # nothing, and without this the loop would otherwise spin flat-out
        # against a single-threaded server for the rest of the 60s budget.
        time.sleep(0.3)
    else:
        _kill(proc)
        raise RuntimeError(f"server did not become ready within 60s:\n{_log_tail_text()}")

    # Dev mode is off at boot by design; the tests need the stub backend.
    # Kill the child before raising on any failure here (a non-2xx/timeout
    # response or a bad body) -- otherwise the subprocess and its port leak
    # forever, and the session-scoped data_dir fixture then deletes the temp
    # directory out from under a process still holding its SQLite files open.
    try:
        resp = requests.post(f"{base}/api/dev-mode", json={"mode": "dev"}, timeout=5)
        assert resp.ok and resp.json().get("mode") == "dev", (
            f"failed to switch the server into dev mode: {resp.status_code} {resp.text}")
    except Exception:
        _kill(proc)
        raise

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def app_server(data_dir):
    yield from _run_app_server(data_dir)


@pytest.fixture
def isolated_app_server(tmp_path):
    """A throwaway app_server + DATA_DIR scoped to this one test.

    Some admin endpoints (e.g. /api/cleanup-orphaned-registrations) have no
    tournament scope -- app.py deletes across every tournament in whatever
    database the server points at. Against the shared session-scoped
    app_server/data_dir, a test that exercises one of those would delete
    rows other tests own, and only survive by luck of file/test ordering
    (it happened to sort last). tmp_path is pytest's own function-scoped
    temp-dir fixture -- reusing it here (rather than hand-rolling another
    tempfile.mkdtemp) means a test requesting both this fixture and tmp_path
    gets the same directory, so it can seed through seed.py and still know
    exactly what's in the database an unscoped endpoint might touch.
    """
    yield from _run_app_server(tmp_path)


@contextlib.contextmanager
def console_errors(page):
    """Collect console errors and uncaught exceptions raised while inside.

    Named handlers so they can be removed again: page.on() without a matching
    remove_listener() keeps them attached (and collecting) after the `with`
    block exits, letting activity outside the measured window fail an
    assertion made after the block.
    """
    found = []

    def _on_console(m):
        if m.type == "error":
            found.append(m.text)

    def _on_pageerror(e):
        found.append(str(e))

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    try:
        yield found
    finally:
        page.remove_listener("console", _on_console)
        page.remove_listener("pageerror", _on_pageerror)
