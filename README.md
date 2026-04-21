# Workaholic

Lightweight Windows daemon that keeps the primary workstation active during
work hours, preventing DeskTime from registering idle gaps when you are
actually working from another device.

---

## 1. What it does

Every ~4 minutes during your work hours, it moves the mouse cursor 1 pixel to
the right and back to its original position. The "nudge" is visually
imperceptible, but the operating system registers it as a valid input event
and DeskTime counts it as activity.

On top of that, while you are within the work window, it **asks Windows not
to sleep or suspend** (keep-awake) — otherwise the process would be frozen
during sleep and an idle gap would still appear in DeskTime.

Outside of work hours the process stays alive but does nothing (**guard**
mode), the keep-awake request is released so the machine can sleep normally,
and no suspicious activity appears at 3 AM or during lunch.

---

## 2. How it works

### 2.1 Heartbeat
- **Mechanism**: `pyautogui.moveRel(1, 0, duration=0.1)` followed by
  `pyautogui.moveRel(-1, 0, duration=0.1)`.
- **Why mouse and not keyboard**: a keystroke could leak characters into
  whatever window you have focused. A 1-px mouse nudge that returns to the
  origin never interferes with typing.
- **Interval**: 240 s (4 min) with a random jitter of ±15 s. DeskTime's
  default idle threshold is 5 min, so 4 min leaves a safety margin. The
  jitter breaks any perfectly mechanical pattern.

### 2.2 Work window
A heartbeat is emitted only when **all** of the following hold:

| Condition   | Value                           |
|-------------|---------------------------------|
| Day of week | Monday through Friday           |
| Time of day | 09:00 – 18:00                   |
| Exception   | Pause 13:00 – 14:00 (lunch)     |

Outside that window the loop sleeps 60 s and re-checks.

### 2.3 Logging
- File: `%USERPROFILE%\workaholic.log` (e.g.
  `C:\Users\USER\workaholic.log`).
- Rotation: up to 1 MB per file, 3 backups kept (`workaholic.log`,
  `workaholic.log.1`, …).
- Format: `YYYY-MM-DD HH:MM:SS [LEVEL] message`.
- Fatal exceptions are captured by `try/except` and written with a full
  traceback before the process exits.

### 2.4 Headless execution
The script is named `workaholic.pyw`. Windows associates the `.pyw`
extension with `pythonw.exe` (console-less Python), so it runs fully in the
background.

### 2.5 Autostart
We don't use the *Startup* folder or the Windows Registry. Instead we use
**Task Scheduler**, which lets us:
- Retry automatically on failure (3 retries, 1 min apart).
- Run on battery as well as AC power.
- Start as soon as the machine is available if it was off at trigger time
  (`StartWhenAvailable`).
- Keep a single instance alive (`MultipleInstances IgnoreNew`).

### 2.6 Keep-awake (prevent sleep/suspend)
If the machine sleeps, the process freezes and cannot send heartbeats — the
DeskTime gap would reappear. To prevent that, when entering the work window
we call the Windows API **`SetThreadExecutionState`** (via `ctypes`) with
these flags:

| Flag                 | Effect                                                |
|----------------------|-------------------------------------------------------|
| `ES_CONTINUOUS`      | The flag persists until it is changed.                |
| `ES_SYSTEM_REQUIRED` | The system does not enter sleep while the flag is set.|

- **Entering** the work window → flag set (machine stays awake).
- **Leaving** (lunch, end of day, weekend) → flag released (machine can
  sleep normally again).
- **On process exit** → a `try/finally` releases the flag even after a fatal
  exception.

Notes:
- **Does not affect the display**: only system sleep is prevented. The
  monitor can still dim/turn off. Add `ES_DISPLAY_REQUIRED` if you also want
  to keep the screen on.
- **No admin required**: any process can request this for itself.
- **Scoped to work hours**: outside the work window the machine sleeps
  normally and saves battery.

---

## 3. Project files

| File                  | Purpose                                                     |
|-----------------------|-------------------------------------------------------------|
| `workaholic.pyw`      | Main script. Runs the heartbeat + guard loop.               |
| `install_task.ps1`    | Registers the `Workaholic` scheduled task on Windows.       |
| `requirements.txt`    | Python dependencies (pyautogui).                            |
| `README.md`           | This document.                                              |
| `CODE_WALKTHROUGH.md` | Line-by-line code explanation (educational, in Spanish).    |
| `LICENSE`             | MIT License.                                                |

---

## 4. Prerequisites

- **Windows 10 / 11**.
- **Python 3.x** installed and on `PATH` (`pythonw.exe` must resolve).
  Verify with:
  ```powershell
  Get-Command pythonw.exe
  ```
- **Administrator privileges** to register the scheduled task.

---

## 5. Installation

Open **PowerShell as Administrator** and run, in order:

```powershell
# 1. Clone the repo (or download the zip and cd into it)
git clone https://github.com/HansAbele/workaholic.git
cd workaholic

# 2. Install the Python dependency
pip install -r requirements.txt

# 3. Register the scheduled task
powershell -ExecutionPolicy Bypass -File .\install_task.ps1

# 4. Start it now (without waiting for next logon)
Start-ScheduledTask -TaskName Workaholic
```

After step 3 you should see in green:
`Scheduled task 'Workaholic' registered. It will run at next logon.`

> **Tip**: if your work hours differ, edit the constants at the top of
> `workaholic.pyw` (see [Configuration](#8-configuration)) **before** step 3.

---

## 6. Verification

Tail the log:

```powershell
Get-Content $env:USERPROFILE\workaholic.log -Wait -Tail 20
```

Within the first 4 minutes (during work hours) you should see:

```
2026-04-21 09:05:12 [INFO] Workaholic started (pid=12345, log=C:\Users\USER\workaholic.log)
2026-04-21 09:05:12 [INFO] Entering work window — heartbeat active; keep-awake ON.
2026-04-21 09:09:07 [INFO] Heartbeat sent (cursor nudge).
2026-04-21 09:13:04 [INFO] Heartbeat sent (cursor nudge).
```

At 13:00: `Outside work window — entering guard mode; keep-awake OFF.`
At 14:00: `Entering work window — heartbeat active; keep-awake ON.`

Press `Ctrl+C` to exit the tail.

---

## 7. Common operations

```powershell
# Task status
Get-ScheduledTask -TaskName Workaholic | Select TaskName, State

# Start manually
Start-ScheduledTask -TaskName Workaholic

# Stop the running process (does not uninstall the task)
Stop-ScheduledTask -TaskName Workaholic

# Show the last 50 log lines
Get-Content $env:USERPROFILE\workaholic.log -Tail 50
```

---

## 8. Configuration

All tunable parameters are declared as constants at the top of
`workaholic.pyw`:

| Constant                      | Default | Description                                   |
|-------------------------------|---------|-----------------------------------------------|
| `HEARTBEAT_INTERVAL_SECONDS`  | 240     | Base interval between heartbeats (s).         |
| `HEARTBEAT_JITTER_SECONDS`    | 15      | Random variation ± (s).                       |
| `MOUSE_NUDGE_PIXELS`          | 1       | Pixels the cursor moves.                      |
| `MOUSE_MOVE_DURATION`         | 0.1     | Duration of each transition (s).              |
| `WORK_DAYS`                   | Mon–Fri | Set of workdays (Mon=0).                      |
| `WORK_START` / `WORK_END`     | 09–18   | Work window.                                  |
| `LUNCH_START` / `LUNCH_END`   | 13–14   | Lunch break.                                  |
| `GUARD_POLL_SECONDS`          | 60      | Re-check frequency outside work hours.        |

After editing, restart the task:

```powershell
Stop-ScheduledTask  -TaskName Workaholic
Start-ScheduledTask -TaskName Workaholic
```

> **Warning**: do not raise `HEARTBEAT_INTERVAL_SECONDS` above 285 s —
> positive jitter could push the actual delay to 300 s, which is DeskTime's
> idle threshold.

---

## 9. Uninstall

Open **PowerShell as Administrator** and run:

```powershell
# 1. Stop and remove the scheduled task
Stop-ScheduledTask       -TaskName Workaholic -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName Workaholic -Confirm:$false

# 2. (Optional) Remove the project files
Remove-Item -Recurse -Force .\workaholic

# 3. (Optional) Remove log files
Remove-Item $env:USERPROFILE\workaholic.log*

# 4. (Optional) Uninstall the Python dependency
pip uninstall pyautogui
```

---

## 10. Troubleshooting

| Symptom                                         | What to check                                                                 |
|-------------------------------------------------|-------------------------------------------------------------------------------|
| `workaholic.log` never appears after starting   | Task is not running: `Get-ScheduledTask -TaskName Workaholic`.                |
| Log shows `ModuleNotFoundError: pyautogui`      | `pip install -r requirements.txt` ran on a different Python than `pythonw.exe`.|
| `install_task.ps1` fails with "Access denied"   | PowerShell was not opened as Administrator.                                   |
| DeskTime still marks idle                       | Check the interval; your org may have a DeskTime idle threshold below 5 min. |
| The cursor visibly jumps                        | Keep `MOUSE_NUDGE_PIXELS` at 1 and/or raise `MOUSE_MOVE_DURATION`.            |
| `Outside work window` in the middle of the day  | Check system time and timezone on Windows.                                    |

To inspect the task's run history:

```powershell
Get-ScheduledTaskInfo -TaskName Workaholic
```

---

## 11. Design notes

- **`pyautogui.FAILSAFE = False`**: pyautogui aborts by default if the
  cursor hits a screen corner. The heartbeat must survive a cursor resting
  in a corner, so we disable the safeguard.
- **`RotatingFileHandler`** instead of `FileHandler`: prevents the log file
  from growing indefinitely.
- **Work-window check every iteration** (not one long sleep): if the system
  clock changes (e.g. DST transition), the guard notices the transition in
  under 60 s.
- **Keep-awake via `SetThreadExecutionState`** instead of changing the
  Windows power plan: (a) no admin required; (b) automatic cleanup — when
  the process dies, Windows reverts to normal behavior; (c) scoped to the
  work window, so energy is still saved after hours.
- **`try/finally` around the loop**: guarantees `set_keep_awake(False)` is
  called on exit, even after a fatal exception, so the system is never left
  in "no sleep" mode after a crash.

---

## License

MIT — see [LICENSE](LICENSE).
