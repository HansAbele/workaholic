"""Workaholic — keeps the main workstation active during work hours so DeskTime
does not register idle gaps while working from another machine.
"""

import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler

import pyautogui

# ---------------------------------------------------------------------------
# Configuration constants — tune these if schedule or behavior needs to change.
# ---------------------------------------------------------------------------

IDLE_THRESHOLD_SECONDS = 180            # Inject activity only if the machine has been idle this long
HEARTBEAT_POLL_SECONDS = 60             # How often to check idle state inside the work window
MOUSE_NUDGE_PIXELS = 25                 # Horizontal displacement for the cursor nudge
MOUSE_MOVE_DURATION = 0.15              # Seconds for each smooth transition
PHANTOM_KEY = "f15"                     # A virtual key that Windows accepts but no normal app reacts to

WORK_DAYS = {0, 1, 2, 3, 4}             # Mon–Fri (Python weekday(): Mon=0)
WORK_START = dtime(9, 0)                # 09:00
WORK_END = dtime(18, 0)                 # 18:00
LUNCH_START = dtime(13, 0)              # 13:00
LUNCH_END = dtime(14, 0)                # 14:00

GUARD_POLL_SECONDS = 60                 # How often to re-check schedule while outside work hours

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


# ---------------------------------------------------------------------------
# Idle detection — use Windows' GetLastInputInfo to tell real user activity
# apart from our own synthetic input.
# ---------------------------------------------------------------------------

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


_last_inject_dwtime = 0  # dwTime that GetLastInputInfo reported right after our last inject


def _read_last_input_dwtime() -> int:
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    return int(info.dwTime)


def current_idle_status() -> tuple[float, bool]:
    """Return (idle seconds, is_our_echo).

    - idle seconds: how long ago was the last input event (real or synthetic).
    - is_our_echo: True when that last input was the one we just injected
      ourselves; lets the caller ignore our own signal when deciding whether
      the user is present.
    """
    if sys.platform != "win32":
        return 0.0, False
    last_input = _read_last_input_dwtime()
    now_tick = int(ctypes.windll.kernel32.GetTickCount())
    idle_ms = (now_tick - last_input) & 0xFFFFFFFF     # handle 32-bit tick wrap
    is_echo = (last_input != 0 and last_input == _last_inject_dwtime)
    return idle_ms / 1000.0, is_echo


def inject_activity() -> None:
    """Emit mouse movement + a phantom key press and record the resulting tick."""
    global _last_inject_dwtime
    pyautogui.moveRel(MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.moveRel(-MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.press(PHANTOM_KEY)
    _last_inject_dwtime = _read_last_input_dwtime()


# ---------------------------------------------------------------------------
# Schedule.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main loop.
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("Workaholic started (pid=%s, log=%s)", os.getpid(), LOG_PATH)
    in_work_window_prev = None
    last_activity_state = None  # "user" or "injected" — used only for transition logging

    try:
        while True:
            now = datetime.now()
            in_work_window = is_within_work_window(now)

            if in_work_window != in_work_window_prev:
                set_keep_awake(in_work_window)
                if in_work_window:
                    logger.info("Entering work window — monitoring idle; keep-awake ON.")
                else:
                    logger.info("Outside work window — entering guard mode; keep-awake OFF.")
                in_work_window_prev = in_work_window
                last_activity_state = None

            if in_work_window:
                idle_s, is_echo = current_idle_status()

                if idle_s >= IDLE_THRESHOLD_SECONDS:
                    try:
                        inject_activity()
                        logger.info(
                            "Machine idle %.0fs — injected activity (mouse + %s).",
                            idle_s, PHANTOM_KEY.upper(),
                        )
                        last_activity_state = "injected"
                    except Exception as exc:
                        logger.exception("Activity injection failed: %s", exc)
                elif not is_echo:
                    if last_activity_state != "user":
                        logger.info(
                            "User activity detected (idle %.0fs) — skipping heartbeat.",
                            idle_s,
                        )
                        last_activity_state = "user"
                # else: our own echo — stay silent, next poll will settle the state

                time.sleep(HEARTBEAT_POLL_SECONDS)
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
