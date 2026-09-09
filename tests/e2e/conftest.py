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


@pytest.fixture(scope="session")
def app_server(data_dir):
    """Boot app.py in dev mode with the network closed off, yield its URL."""
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
        iterate it ("deque mutated during iteration") -- on the one path
        that must report a real startup failure. Once stdout closes the
        thread's for-loop hits EOF and returns almost immediately.
        """
        drain_thread.join(timeout=5)
        return b"".join(log_tail).decode(errors="replace")

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
        proc.kill()
        proc.wait(timeout=10)
        raise RuntimeError(f"server did not become ready within 60s:\n{_log_tail_text()}")

    # Dev mode is off at boot by design; the tests need the stub backend.
    resp = requests.post(f"{base}/api/dev-mode", json={"mode": "dev"}, timeout=5)
    assert resp.ok and resp.json().get("mode") == "dev", (
        f"failed to switch the server into dev mode: {resp.status_code} {resp.text}")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@contextlib.contextmanager
def console_errors(page):
    """Collect console errors and uncaught exceptions raised while inside."""
    found = []
    page.on("console", lambda m: found.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: found.append(str(e)))
    yield found
