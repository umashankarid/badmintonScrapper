"""
Boundary for every Badminton Sweden interaction.

app.py talks only to this module. It dispatches each call to bwf_live (real
scraping) or bwf_dev (stubs), depending on the current mode.

Mode rules:
- DEV_TOOLS unset  -> always "live". This is production; the toggle does not exist.
- DEV_TOOLS=1      -> starts "live", switchable at runtime via set_mode().

The mode is deliberately not persisted: every restart returns to live.
"""

import logging
import os

logger = logging.getLogger(__name__)

VALID_MODES = ("live", "dev")

_mode = "live"


def dev_tools_enabled():
    """True when this server is allowed to offer a development mode at all."""
    return os.environ.get("DEV_TOOLS", "").lower() in ("1", "true", "yes")


def get_mode():
    """The mode in effect for this request. Always 'live' in production."""
    if not dev_tools_enabled():
        return "live"
    return _mode


def set_mode(mode):
    """Switch mode. Returns the mode now in effect."""
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown mode {mode!r}, expected one of {VALID_MODES}")
    global _mode
    _mode = mode
    logger.info(f"🔀 BWF mode set to: {mode}")
    return get_mode()


import bwf_dev
import bwf_live

# Re-exported so app.py can distinguish these from a transport failure without
# importing bwf_live directly.
from bwf_live import LoginPageUnavailable, ProfileNotFound


def _backend():
    """The module that services calls right now."""
    return bwf_dev if get_mode() == "dev" else bwf_live


def get_player_license(player_name):
    return _backend().get_player_license(player_name)


def get_player_ranking(player_name):
    return _backend().get_player_ranking(player_name)


def login(username, password):
    return _backend().login(username, password)


def verify_credentials(username, password):
    return _backend().verify_credentials(username, password)
