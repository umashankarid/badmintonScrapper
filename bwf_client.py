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
