# Workaholic

Lightweight Windows daemon that keeps the primary workstation active during
work hours, preventing DeskTime from registering idle gaps when you are
actually working from another device.

---

## 1. What it does

During your work hours, Workaholic watches how long the machine has been
idle using the Windows API `GetLastInputInfo`:

- **If you are using the machine** (last real input was recent), it does
  nothing. No interference with your real work.
- **If the machine has been idle for 3 minutes** (under DeskTime's 5-minute
  threshold, with a safety margin), it injects a short burst of activity:
  a ~25 px horizontal mouse movement with smooth interpolation, plus an
  `F15` key press. The mouse movement is visually imperceptible; `F15` is a
  valid virtual key that no normal application reacts to, so neither event
  disrupts anything you might have open.

On top of that, while you are within the work window, it **asks Windows not
to sleep or suspend** (keep-awake) — otherwise the process would be frozen
during sleep and an idle gap would still appear in DeskTime.

Outside of work hours the process stays alive but does nothing (**guard**
mode), the keep-awake request is released so the machine can sleep normally,
and no suspicious activity appears at 3 AM or during lunch.

---

## 2. How it works

### 2.1 Heartbeat
When the machine has been truly idle for `IDLE_THRESHOLD_SECONDS` (default
180 s), Workaholic emits **three input signals in sequence** to maximize the
chance the monitor accepts it as activity:

1. `pyautogui.moveRel(25, 0, duration=0.15)` — move the cursor 25 px to the
   right with a smooth transition (multiple intermediate events, like a
   human hand).
2. `pyautogui.moveRel(-25, 0, duration=0.15)` — return the cursor to the
   original position.
3. `pyautogui.press("f15")` — a phantom key press. `F15` is a valid
   Windows virtual key that practically no desktop application binds to,
   so it registers as input without triggering anything.

The three channels together (mouse X axis + keyboard) usually satisfy
monitors that filter out "too small" mouse movements or "mouse-only"
signals. The 25 px / 0.15 s speed sits in the range of plausible human
cursor motion (~167 px/s).

### 2.2 Idle detection (skip when the user is present)
Before every possible injection, Workaholic reads the actual system-wide
idle time via `GetLastInputInfo`:

| State                                    | What Workaholic does                    |
|------------------------------------------|------------------------------------------|
| Idle < `IDLE_THRESHOLD_SECONDS`          | Skip — the user is using the machine.    |
| Idle ≥ `IDLE_THRESHOLD_SECONDS`          | Inject the heartbeat described above.    |
| Idle is low, but the last event was ours | Skip the "user active" log (our echo).   |

Because our own injection updates `GetLastInputInfo`, Workaholic records
the `dwTime` it produced and compares against it on the next poll. That
way the logs can distinguish **our echo** from **a real user typing**.

Why 180 s? It lives comfortably below DeskTime's 300 s idle threshold even
accounting for the 60 s poll interval (180 + 60 + ~1 s = 241 s worst case,
still ~59 s of margin before DeskTime would mark idle). It is also above
the 30–120 s pauses that happen while a user is reading, thinking, or
briefly stepping away — avoiding injections that would fight with real
work.

### 2.3 Work window
Heartbeats are considered only when **all** of the following hold:

| Condition   | Value                           |
|-------------|---------------------------------|
| Day of week | Monday through Friday           |
| Time of day | 09:00 – 18:00                   |
| Exception   | Pause 13:00 – 14:00 (lunch)     |

Outside that window the loop sleeps 60 s and re-checks.

### 2.4 Logging
- File: `%USERPROFILE%\workaholic.log` (e.g.
  `C:\Users\USER\workaholic.log`).
- Rotation: up to 1 MB per file, 3 backups kept (`workaholic.log`,
  `workaholic.log.1`, …).
- Format: `YYYY-MM-DD HH:MM:SS [LEVEL] message`.
- Fatal exceptions are captured by `try/except` and written with a full
  traceback before the process exits.

### 2.5 Headless execution
The script is named `workaholic.pyw`. Windows associates the `.pyw`
extension with `pythonw.exe` (console-less Python), so it runs fully in the
background.

### 2.6 Autostart
We don't use the *Startup* folder or the Windows Registry. Instead we use
**Task Scheduler**, which lets us:
- Retry automatically on failure (3 retries, 1 min apart).
- Run on battery as well as AC power.
- Start as soon as the machine is available if it was off at trigger time
  (`StartWhenAvailable`).
- Keep a single instance alive (`MultipleInstances IgnoreNew`).

### 2.7 Keep-awake (prevent sleep/suspend)
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

During work hours you should see a timeline similar to this, depending on
whether you are physically at the machine:

```
2026-04-21 09:00:02 [INFO] Workaholic started (pid=12345, log=C:\Users\USER\workaholic.log)
2026-04-21 09:00:02 [INFO] Entering work window — monitoring idle; keep-awake ON.
2026-04-21 09:01:02 [INFO] User activity detected (idle 8s) — skipping heartbeat.
2026-04-21 11:18:05 [INFO] Machine idle 183s — injected activity (mouse + F15).
2026-04-21 11:22:06 [INFO] Machine idle 180s — injected activity (mouse + F15).
2026-04-21 11:40:07 [INFO] User activity detected (idle 4s) — skipping heartbeat.
```

- `User activity detected` — real input happened recently; we stay out of
  the way.
- `Machine idle Ns — injected activity` — we emitted the mouse + `F15`
  burst because nobody had touched the machine for `N` seconds.

At 13:00: `Outside work window — entering guard mode; keep-awake OFF.`
At 14:00: `Entering work window — monitoring idle; keep-awake ON.`

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

| Constant                      | Default | Description                                        |
|-------------------------------|---------|----------------------------------------------------|
| `IDLE_THRESHOLD_SECONDS`      | 180     | Minimum idle time before we inject activity.       |
| `HEARTBEAT_POLL_SECONDS`      | 60      | How often to check idle state inside work hours.   |
| `MOUSE_NUDGE_PIXELS`          | 25      | Horizontal displacement for the cursor nudge.      |
| `MOUSE_MOVE_DURATION`         | 0.15    | Duration of each smooth transition (s).            |
| `PHANTOM_KEY`                 | `f15`   | Virtual key that Windows accepts, apps ignore.     |
| `WORK_DAYS`                   | Mon–Fri | Set of workdays (Mon=0).                           |
| `WORK_START` / `WORK_END`     | 09–18   | Work window.                                       |
| `LUNCH_START` / `LUNCH_END`   | 13–14   | Lunch break.                                       |
| `GUARD_POLL_SECONDS`          | 60      | Re-check frequency outside work hours.             |

After editing, restart the task:

```powershell
Stop-ScheduledTask  -TaskName Workaholic
Start-ScheduledTask -TaskName Workaholic
```

> **Warning**: keep `IDLE_THRESHOLD_SECONDS + HEARTBEAT_POLL_SECONDS` below
> DeskTime's idle threshold (300 s) with a safety margin. Default values
> leave ~59 s of margin. If you raise the threshold, test carefully.

> **Tip**: if `F15` triggers something in your workflow (rare — usually only
> specialized music or gaming software), swap `PHANTOM_KEY` to `"f24"` or
> `"scrolllock"`.

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
| DeskTime still marks idle even with injections  | Your monitor likely filters synthetic input (`LLMHF_INJECTED` flag). No user-mode Python workaround exists; an Arduino/HID device is needed. |
| Logs never say "Machine idle Ns — injected"     | You are actively using the machine — that is correct behavior, no injection is needed. Walk away for >3 min to test. |
| The cursor visibly jumps during an injection    | Lower `MOUSE_NUDGE_PIXELS` or raise `MOUSE_MOVE_DURATION`.                    |
| `F15` is intercepted by something               | Change `PHANTOM_KEY` to `"f24"` or `"scrolllock"` in the script.              |
| `Outside work window` in the middle of the day  | Check system time and timezone on Windows.                                    |

To inspect the task's run history:

```powershell
Get-ScheduledTaskInfo -TaskName Workaholic
```

---

## 11. Design notes

- **Idle-driven, not interval-driven**: earlier versions injected every
  ~4 minutes regardless. That competes with real user activity and is
  wasteful. The current design reads `GetLastInputInfo` and only acts when
  the machine has been genuinely idle past a threshold.
- **Three-channel heartbeat (mouse X + return + `F15`)**: a single 1-px
  move was too subtle to convince some monitors. Using a larger,
  interpolated movement plus a phantom key press maximizes the chance the
  event is registered without producing any visible side effect.
- **Echo suppression**: our own synthetic input updates
  `GetLastInputInfo`. The script records the exact `dwTime` it produced
  and compares it against subsequent reads, so logs can tell a real user
  from our own echo.
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
- **Known limitation — `LLMHF_INJECTED`**: some productivity monitors
  install a low-level mouse/keyboard hook and reject events with the
  `LLMHF_INJECTED` flag set. Every user-mode method of synthesizing input
  on Windows (`SendInput`, `mouse_event`, `keybd_event`, pyautogui, AutoIt,
  …) sets that flag. If the monitor uses that filter, no pure-software
  solution will work — a hardware HID device (e.g. Arduino Leonardo
  emulating a USB mouse/keyboard) is the only option.

---

## License

MIT — see [LICENSE](LICENSE).
