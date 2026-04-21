"""Workaholic — keeps the main workstation active during work hours so DeskTime
does not register idle gaps while working from another machine.
"""

import ctypes
import logging
import os
import random
import sys
import time
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler

import pyautogui

# ---------------------------------------------------------------------------
# Configuration constants — tune these if schedule or behavior needs to change.
# ---------------------------------------------------------------------------

HEARTBEAT_INTERVAL_SECONDS = 240        # 4 min base interval (under DeskTime's 5 min idle)
HEARTBEAT_JITTER_SECONDS = 15           # ±15 s random jitter to avoid a mechanical pattern
MOUSE_NUDGE_PIXELS = 1                  # Horizontal displacement (imperceptible)
MOUSE_MOVE_DURATION = 0.1               # Seconds for each smooth transition

WORK_DAYS = {0, 1, 2, 3, 4}             # Mon–Fri (Python weekday(): Mon=0)
WORK_START = dtime(9, 0)                # 09:00
WORK_END = dtime(18, 0)                 # 18:00
LUNCH_START = dtime(13, 0)              # 13:00
LUNCH_END = dtime(14, 0)                # 14:00

GUARD_POLL_SECONDS = 60                 # How often to re-check schedule while idle/guard

LOG_FILENAME = "workaholic.log"
LOG_PATH = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), LOG_FILENAME)

# ---------------------------------------------------------------------------
# Logging setup — file-only, since .pyw has no console.
# ---------------------------------------------------------------------------

logger = logging.getLogger("workaholic")
logger.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_handler)

# Disable pyautogui's fail-safe (corner-hit abort) since nudges are tiny and
# the script must survive a cursor that happens to rest in a screen corner.
pyautogui.FAILSAFE = False

# ---------------------------------------------------------------------------
# Keep-awake — ask Windows not to sleep/suspend while we're in the work window.
# ---------------------------------------------------------------------------

ES_CONTINUOUS = 0x80000000        # Flag persists until changed
ES_SYSTEM_REQUIRED = 0x00000001   # Prevent system sleep (display can still dim)


def set_keep_awake(enabled: bool) -> None:
    """Tell Windows to stay awake while enabled; release the request when not."""
    if sys.platform != "win32":
        return
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if enabled else ES_CONTINUOUS
    if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0:
        logger.warning("SetThreadExecutionState returned 0 (call failed).")


def is_within_work_window(now: datetime) -> bool:
    """True only during Mon–Fri work hours, excluding the lunch hour."""
    if now.weekday() not in WORK_DAYS:
        return False
    current = now.time()
    if not (WORK_START <= current < WORK_END):
        return False
    if LUNCH_START <= current < LUNCH_END:
        return False
    return True


def nudge_mouse() -> None:
    """Move the cursor 1 px right and back with a smooth transition."""
    pyautogui.moveRel(MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.moveRel(-MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)


def next_heartbeat_delay() -> float:
    jitter = random.uniform(-HEARTBEAT_JITTER_SECONDS, HEARTBEAT_JITTER_SECONDS)
    return HEARTBEAT_INTERVAL_SECONDS + jitter


def run() -> None:
    logger.info("Workaholic started (pid=%s, log=%s)", os.getpid(), LOG_PATH)
    in_work_window_prev = None

    try:
        while True:
            now = datetime.now()
            in_work_window = is_within_work_window(now)

            if in_work_window != in_work_window_prev:
                set_keep_awake(in_work_window)
                if in_work_window:
                    logger.info("Entering work window — heartbeat active; keep-awake ON.")
                else:
                    logger.info("Outside work window — entering guard mode; keep-awake OFF.")
                in_work_window_prev = in_work_window

            if in_work_window:
                try:
                    nudge_mouse()
                    logger.info("Heartbeat sent (cursor nudge).")
                except Exception as exc:
                    logger.exception("Heartbeat failed: %s", exc)
                time.sleep(next_heartbeat_delay())
            else:
                time.sleep(GUARD_POLL_SECONDS)
    finally:
        set_keep_awake(False)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Workaholic stopped by user (KeyboardInterrupt).")
    except Exception as exc:
        logger.critical("Fatal error — Workaholic is terminating: %s", exc, exc_info=True)
        sys.exit(1)
