# Workaholic — Walkthrough línea por línea

Documento educativo. Explica **cada línea** de los dos archivos del proyecto:
por qué está ahí, qué concepto de Python / PowerShell está usando, y qué pasa
si la cambias.

---

## Parte 1 — `workaholic.pyw`

### Docstring del módulo (líneas 1–3)

```python
"""Workaholic — keeps the main workstation active during work hours so DeskTime
does not register idle gaps while working from another machine.
"""
```

- Las comillas triples `"""..."""` crean una **cadena multilinea**. Cuando
  aparece como primera sentencia de un archivo se convierte en el **docstring
  del módulo**: queda accesible en `workaholic.__doc__` y la usan
  herramientas como `help()` o Sphinx.
- No se ejecuta nada: es metadatos del archivo.

### Imports (líneas 5–14)

```python
import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler

import pyautogui
```

- `ctypes`: permite llamar funciones de librerías nativas (DLLs en Windows,
  `.so` en Linux). Lo usamos para invocar `SetThreadExecutionState`,
  `GetLastInputInfo` y `GetTickCount` del kernel/user32 de Windows.
- `logging`: módulo estándar para registrar eventos en archivos / consola.
- `os`: acceso al sistema operativo (variables de entorno, rutas, PID).
- `sys`: acceso al intérprete (`sys.exit`, `sys.platform`).
- `time`: funciones de tiempo; aquí solo `time.sleep()`.
- `from ctypes import wintypes`: subpaquete con los tipos primitivos de la
  Win32 API (`UINT`, `DWORD`, `HANDLE`, …). Los usamos para declarar la
  estructura `LASTINPUTINFO` con los tipos correctos.
- `from datetime import datetime, time as dtime`
  - Importa **dos cosas** del módulo `datetime`:
    - `datetime`: clase para fecha+hora.
    - `time`: clase para "solo hora del día" — pero como ya importamos
      arriba el **módulo** llamado `time`, renombramos con `as dtime` para
      evitar colisión de nombres.
- `from logging.handlers import RotatingFileHandler`: handler de logging que
  rota el archivo cuando supera cierto tamaño.
- Línea en blanco antes de `import pyautogui`: convención PEP 8 —
  stdlib primero, luego librerías de terceros, separadas por una línea.

### Bloque de constantes (líneas 16–35)

```python
IDLE_THRESHOLD_SECONDS = 180
HEARTBEAT_POLL_SECONDS = 60
MOUSE_NUDGE_PIXELS = 25
MOUSE_MOVE_DURATION = 0.15
PHANTOM_KEY = "f15"
```

- **Convención PEP 8**: MAYÚSCULAS_CON_GUIONES_BAJOS = constante. Python no
  lo impone pero es señal para el lector.
- `IDLE_THRESHOLD_SECONDS = 180` → solo inyectamos actividad cuando la
  máquina lleva ≥ 180 s sin input real. Por debajo del umbral de DeskTime
  (300 s) con margen suficiente para el polling.
- `HEARTBEAT_POLL_SECONDS = 60` → cada minuto chequeamos el idle. Con esto,
  el peor caso entre "idle cumple el umbral" y "DeskTime nos marcaría idle"
  es 180 + 60 ≈ 240 s, muy por debajo de 300 s.
- `MOUSE_NUDGE_PIXELS = 25` → era 1 en la v1. Demasiado pequeño: algunos
  monitores descartan movimientos <5 px como "drift". 25 px es
  imperceptible a simple vista pero suficiente para que el monitor lo
  cuente.
- `MOUSE_MOVE_DURATION = 0.15` → `pyautogui` interpola el movimiento en ese
  tiempo. Varios eventos intermedios = aspecto más humano.
- `PHANTOM_KEY = "f15"` → una *virtual key* válida que Windows acepta, pero
  que ningún software convencional usa (los teclados físicos suelen llegar
  hasta F12). `pyautogui.press("f15")` envía press+release de esa tecla.

```python
WORK_DAYS = {0, 1, 2, 3, 4}
WORK_START = dtime(9, 0)
WORK_END = dtime(18, 0)
LUNCH_START = dtime(13, 0)
LUNCH_END = dtime(14, 0)
GUARD_POLL_SECONDS = 60
```

- Llaves sueltas `{a, b, c}` = **set**, pertenencia O(1).
- `weekday()` devuelve 0 (lunes) a 6 (domingo). Este set = Mon–Fri.
- `dtime(9, 0)` crea un `datetime.time` (solo hora, sin fecha). Comparables
  con `<`, `<=`.
- `GUARD_POLL_SECONDS` es la frecuencia de chequeo fuera del horario
  laboral. Un minuto es suficiente para reaccionar a transiciones
  (empezar jornada, fin de almuerzo, etc.).

```python
LOG_FILENAME = "workaholic.log"
LOG_PATH = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), LOG_FILENAME)
```

- `os.environ.get(var, fallback)` lee una variable de entorno con valor por
  defecto. `USERPROFILE` en Windows = `C:\Users\USER`. En Linux/Mac el
  fallback `expanduser("~")` resuelve a la home del usuario.
- `os.path.join` concatena con el separador nativo del OS.

### Setup de logging (líneas 41–47)

```python
logger = logging.getLogger("workaholic")
logger.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_handler)
```

- `getLogger("workaholic")` devuelve un logger nombrado (singleton por
  nombre). Evita interferir con el logger raíz.
- `setLevel(INFO)` descarta DEBUG. Jerarquía:
  `DEBUG < INFO < WARNING < ERROR < CRITICAL`.
- `RotatingFileHandler`: rota a `.1`, `.2`, `.3` cuando supera 1 MB;
  descarta el más viejo.
- `1_000_000`: el guion bajo en números enteros es un separador de miles
  (Python 3.6+). Solo estético.
- `encoding="utf-8"` evita problemas con tildes y caracteres no-ASCII en
  Windows (cp1252 por defecto).
- El `Formatter` define la plantilla. `%(asctime)s`, `%(levelname)s`,
  `%(message)s` son placeholders del módulo `logging`.

### Desactivar el fail-safe de pyautogui (líneas 49–51)

```python
pyautogui.FAILSAFE = False
```

Por defecto pyautogui aborta con excepción si el cursor toca una esquina de
la pantalla (mecanismo de "pánico"). Como Workaholic puede inyectar
movimientos cuando el cursor está descansando en una esquina, lo
desactivamos.

### Keep-awake (líneas 53–67)

```python
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
```

- Constantes de Win32 (definidas en `winuser.h`). Python no las trae; las
  declaramos con sus valores exactos en hex.
- `0x80000000` y `0x00000001` se combinan con OR bit a bit (`|`).

```python
def set_keep_awake(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if enabled else ES_CONTINUOUS
    if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0:
        logger.warning("SetThreadExecutionState returned 0 (call failed).")
```

- `sys.platform == "win32"` también en Windows de 64 bits (nombre
  histórico). Early-return en otras plataformas.
- **Ternario**: `A if cond else B`.
- `ctypes.windll.kernel32.SetThreadExecutionState(flags)` → llamada nativa
  a `kernel32.dll`. No requiere admin.
- Retorno 0 = fallo; logueamos warning pero no reventamos.

### Idle detection — `_LASTINPUTINFO` (líneas 70–90)

```python
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]
```

- Replica de la struct C `LASTINPUTINFO` de `winuser.h`:
  ```c
  typedef struct tagLASTINPUTINFO {
      UINT  cbSize;
      DWORD dwTime;
  } LASTINPUTINFO;
  ```
- `ctypes.Structure` es la clase base para structs nativas. `_fields_` es
  la convención de ctypes para declarar los campos en orden y con tipos.
- El guion bajo inicial (`_LASTINPUTINFO`) indica "privado / detalle de
  implementación".

```python
_last_inject_dwtime = 0
```

- Variable module-level. Guarda el `dwTime` que Windows produjo
  inmediatamente después de nuestra última inyección.
- Sirve para distinguir **nuestro eco** (nosotros movimos el mouse) de
  **input real del usuario** (alguien escribió).

```python
def _read_last_input_dwtime() -> int:
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    return int(info.dwTime)
```

- `info = _LASTINPUTINFO()` → instancia la struct (todos los campos a 0).
- `cbSize = ctypes.sizeof(...)` → la API de Windows requiere que el llamante
  le diga el tamaño de la struct (versionado hacia atrás).
- `ctypes.byref(info)` → pasa "por referencia" (puntero), igual a `&info`
  en C. La API necesita escribir en esa memoria.
- `GetLastInputInfo` devuelve nonzero si tuvo éxito. Si falla, devolvemos 0
  (caller decide cómo tratarlo).
- `int(info.dwTime)` → convierte del tipo ctypes a int de Python.

### Idle detection — `current_idle_status` (líneas 93–107)

```python
def current_idle_status() -> tuple[float, bool]:
    """Return (idle seconds, is_our_echo)."""
    if sys.platform != "win32":
        return 0.0, False
    last_input = _read_last_input_dwtime()
    now_tick = int(ctypes.windll.kernel32.GetTickCount())
    idle_ms = (now_tick - last_input) & 0xFFFFFFFF
    is_echo = (last_input != 0 and last_input == _last_inject_dwtime)
    return idle_ms / 1000.0, is_echo
```

- `tuple[float, bool]` anotación: devuelve una tupla con un float y un
  bool. Python 3.9+ permite esta sintaxis.
- `GetTickCount()` → tiempo desde el arranque de Windows en milisegundos
  (DWORD, 32 bits, envuelve cada ~49.7 días).
- **Manejo del wrap**: al restar dos tick counts en Python, podrías obtener
  un número negativo si el tick wrappeó entre una captura y otra. El AND
  con `0xFFFFFFFF` fuerza el resultado a 32 bits unsigned, que es la forma
  correcta de comparar tick counts según la doc de Microsoft.
- `is_echo`: cierto solo si tenemos un `_last_inject_dwtime` guardado
  (`!= 0`) y coincide exactamente con el `dwTime` actual. Eso significa
  "nadie ha metido input después de nosotros" = el último evento fue
  nuestro.

### Idle detection — `inject_activity` (líneas 110–116)

```python
def inject_activity() -> None:
    global _last_inject_dwtime
    pyautogui.moveRel(MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.moveRel(-MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.press(PHANTOM_KEY)
    _last_inject_dwtime = _read_last_input_dwtime()
```

- `global _last_inject_dwtime` → sin esta declaración, Python trataría la
  asignación `_last_inject_dwtime = ...` como una nueva variable local.
- **3 canales de input**:
  1. Mouse 25 px a la derecha con interpolación de 0.15 s (varios eventos
     intermedios).
  2. Mouse 25 px a la izquierda (vuelta al origen).
  3. Tecla fantasma `F15` (press+release completo con `pyautogui.press`).
- Tres señales maximizan la probabilidad de que el monitor lo cuente, sin
  efectos visibles: el neto del mouse es 0 y `F15` no dispara nada en
  software normal.
- Justo después grabamos el `dwTime` que Windows nos acaba de poner. En el
  siguiente `current_idle_status()`, si `dwTime` coincide sabemos que no
  hubo input real entre medias.

### Función `is_within_work_window` (líneas 123–132)

```python
def is_within_work_window(now: datetime) -> bool:
    if now.weekday() not in WORK_DAYS:
        return False
    current = now.time()
    if not (WORK_START <= current < WORK_END):
        return False
    if LUNCH_START <= current < LUNCH_END:
        return False
    return True
```

- `now: datetime` → anotación de tipo. Python no la chequea en runtime,
  pero documenta la intención.
- Encadenamiento de comparaciones: `A <= x < B` equivale a
  `(A <= x) and (x < B)`.
- Usamos `<` (estricto) en `WORK_END`: a las 18:00:00 en punto el horario
  se acabó. Si fuera `<=`, a las 18:00:00.000 aún pasaría.
- Misma idea invertida para el almuerzo.

### Función `run` — el loop principal (líneas 139–184)

```python
def run() -> None:
    logger.info("Workaholic started (pid=%s, log=%s)", os.getpid(), LOG_PATH)
    in_work_window_prev = None
    last_activity_state = None
```

- `logger.info(fmt, *args)` — pasarle args separados (no f-string) es más
  eficiente: si INFO estuviera deshabilitado, `logging` no gasta tiempo
  formateando.
- `in_work_window_prev` y `last_activity_state` → estado previo para
  detectar **transiciones** y logear solo cuando cambia algo.
- `None` es el valor "aún no sabemos", garantiza que la primera iteración
  loguee lo que corresponda.

```python
    try:
        while True:
```

- El `try ... finally` al final garantiza que `set_keep_awake(False)` se
  llame siempre al salir del loop (por excepción, KeyboardInterrupt, lo
  que sea).
- `while True` = loop infinito.

```python
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
```

- Solo actuamos en **transiciones** (entrada y salida del horario laboral).
- Al transicionar aplicamos `set_keep_awake` y reseteamos
  `last_activity_state` (porque el "estado de actividad del usuario" del
  día anterior no tiene sentido el día siguiente).

```python
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
```

- **Rama 1 — idle ≥ umbral**: inyectamos y logueamos con el idle medido.
- El `try/except` garantiza que un fallo de pyautogui no mate el loop
  entero. `logger.exception` escribe el traceback completo.
- Guardamos "injected" como último estado. Sirve para el transition
  logging.

```python
                elif not is_echo:
                    if last_activity_state != "user":
                        logger.info(
                            "User activity detected (idle %.0fs) — skipping heartbeat.",
                            idle_s,
                        )
                        last_activity_state = "user"
                # else: our own echo — stay silent, next poll will settle the state
```

- **Rama 2 — idle bajo y NO es nuestro eco**: es usuario real.
  Solo logueamos **una vez** cuando cambia el estado (evita 480 líneas/día
  de "usuario activo").
- **Rama 3 (implícita) — idle bajo y ES nuestro eco**: silencio. El propio
  echo se consumirá en el siguiente poll (idle crecerá y eventualmente
  entraremos en rama 1 o rama 2).

```python
                time.sleep(HEARTBEAT_POLL_SECONDS)
            else:
                time.sleep(GUARD_POLL_SECONDS)
```

- Dentro del horario chequeamos cada 60 s (`HEARTBEAT_POLL_SECONDS`).
- Fuera del horario también 60 s (`GUARD_POLL_SECONDS`), pero
  semánticamente separados para poder ajustarlos independientemente.

```python
    finally:
        set_keep_awake(False)
```

- El `finally` **siempre** se ejecuta al salir del `try`, pase lo que pase.
- Garantiza liberar el flag de keep-awake antes de que el proceso muera.

### Bloque principal (líneas 187–194)

```python
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Workaholic stopped by user (KeyboardInterrupt).")
    except Exception as exc:
        logger.critical("Fatal error — Workaholic is terminating: %s", exc, exc_info=True)
        sys.exit(1)
```

- `__name__` es `"__main__"` cuando ejecutas directamente, y el nombre
  del módulo cuando importas. El guardián permite importar el archivo
  sin ejecutar el loop (útil para tests).
- Ctrl+C se loguea como parada limpia.
- Cualquier otra excepción → CRITICAL con traceback (`exc_info=True`) y
  `sys.exit(1)`. El código 1 se lo devolvemos al Programador de Tareas,
  que aplicará su política de reintento.

---

## Parte 2 — `install_task.ps1`

### Comentarios iniciales (líneas 1–2)

```powershell
# Registers the "Workaholic" scheduled task so workaholic.pyw starts at logon.
# Run once from an elevated PowerShell: powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```

En PowerShell, `#` inicia un comentario de una línea.

### Modo estricto de errores (línea 4)

```powershell
$ErrorActionPreference = "Stop"
```

- Variable automática. Default: `"Continue"` (los errores no terminales se
  imprimen pero el script sigue).
- Con `"Stop"`, cualquier error se convierte en terminante. Evita dejar
  una instalación a medias.

### Variables de configuración (líneas 6–7)

```powershell
$TaskName    = "Workaholic"
$ScriptPath  = Join-Path $PSScriptRoot "workaholic.pyw"
```

- Las variables en PowerShell llevan `$`.
- `$PSScriptRoot` es una variable automática con la carpeta donde vive
  el `.ps1`, independiente del CWD.
- `Join-Path a b` = `os.path.join(a, b)`.

### Validación de que el script existe (líneas 9–11)

```powershell
if (-not (Test-Path $ScriptPath)) {
    throw "workaholic.pyw not found at $ScriptPath"
}
```

- `Test-Path` → `$true`/`$false`.
- `-not` = negación lógica.
- `throw` lanza una excepción; con `$ErrorActionPreference = "Stop"`,
  aborta.

### Resolver `pythonw.exe` (líneas 13–18)

```powershell
$PythonwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if (-not $PythonwCmd) {
    throw "pythonw.exe not found on PATH. Install Python and ensure it is on PATH."
}
$Pythonw = $PythonwCmd.Source
```

- `Get-Command` = `which` en Unix.
- `-ErrorAction SilentlyContinue` evita que reviente; devuelve `$null` si
  no lo encuentra.
- `.Source` = ruta absoluta del ejecutable.

### Definir la acción (línea 20)

```powershell
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$ScriptPath`""
```

- `New-ScheduledTaskAction` arma el objeto "qué ejecutar".
- `` `" `` = escape de comilla doble dentro de un string entre comillas
  dobles. Envolvemos la ruta en comillas literales para que funcione aun
  con espacios.

### Definir el trigger (línea 22)

```powershell
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
```

- `-AtLogOn` = arranca al iniciar sesión.
- `$env:USERNAME` lee la env var `USERNAME`.
- Restringe el trigger a **tu** usuario — no se dispara con logons de
  otros usuarios en la misma máquina.

### Definir los settings (líneas 24–31)

```powershell
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -MultipleInstances IgnoreNew
```

- El `` ` `` al final de cada línea = continuador de línea en PowerShell
  (equivalente a `\` en bash).
- `-AllowStartIfOnBatteries` — por defecto Windows no arranca tareas en
  batería. Lo habilitamos.
- `-DontStopIfGoingOnBatteries` — no la mates si pasas a batería.
- `-StartWhenAvailable` — si el equipo estaba apagado al trigger, arranca
  en cuanto se encienda.
- `-RestartCount 3` + `-RestartInterval 1min` — 3 reintentos con 1 min
  entre cada uno si la tarea falla.
- `-ExecutionTimeLimit 0 días` — sin límite (default: 72 h). Es un
  daemon, lo queremos eterno.
- `-MultipleInstances IgnoreNew` — si ya corre, ignora triggers extra.

### Definir el principal (línea 33)

```powershell
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
```

- `-LogonType Interactive` → requiere sesión de usuario activa.
- `-RunLevel Limited` → permisos normales (no admin). Mover el mouse no
  requiere elevación; mínimo privilegio.

### Limpieza si la tarea ya existe (líneas 35–37)

```powershell
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
```

- Idempotencia: puedes correr el instalador múltiples veces sin error.
- `-Confirm:$false` evita el prompt "¿seguro?".

### Registrar la tarea (líneas 39–45)

```powershell
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Keeps the workstation active during work hours so DeskTime does not register idle gaps." | Out-Null
```

- Ensambla los objetos que armamos arriba.
- `| Out-Null` descarta el objeto que `Register-ScheduledTask` devuelve
  (evita basura en consola).

### Mensajes al usuario (líneas 47–50)

```powershell
Write-Host "Scheduled task '$TaskName' registered. It will run at next logon." -ForegroundColor Green
Write-Host "To start it now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "To stop it:        Stop-ScheduledTask  -TaskName $TaskName"
Write-Host "To remove it:      Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
```

- `Write-Host` escribe a consola. `-ForegroundColor Green` tiñe.
- Variables `$...` se expanden dentro de comillas dobles.
- En la última línea `` `$false `` escapa el `$` para que salga literal
  (no lo queremos expandir al valor booleano).

---

## Resumen de patrones que aparecen en el código

| Patrón                       | Dónde aparece             | Por qué                                              |
|------------------------------|---------------------------|------------------------------------------------------|
| Constantes al inicio         | workaholic.pyw 20–32      | Fácil de tunear sin buscar en la lógica.             |
| Guard `if __name__ == ...`   | workaholic.pyw 187        | Permite importar el módulo sin ejecutar el loop.     |
| `try/except` en inyección    | workaholic.pyw 162–170    | Un fallo de pyautogui no debe matar el daemon.       |
| `try/finally` en loop        | workaholic.pyw 144–184    | Garantiza cleanup de keep-awake al salir.            |
| `try/except` top-level       | workaholic.pyw 188–194    | Fatales quedan logueados antes de morir.             |
| Rotación de log              | workaholic.pyw 43         | Evita archivo que crece sin límite.                  |
| Guard por plataforma         | workaholic.pyw 63, 101    | Script sigue corriendo en Linux/Mac sin petar.       |
| Llamada a Win32 vía `ctypes` | workaholic.pyw 66, 88, 104| Acceso a APIs sin librerías extra.                   |
| Struct C con `ctypes`        | workaholic.pyw 75–79      | Replica `LASTINPUTINFO` para `GetLastInputInfo`.     |
| Echo suppression (tracking)  | workaholic.pyw 82, 106, 116 | Distingue nuestro propio input del del usuario.    |
| Detección de transición      | workaholic.pyw 149–156, 172–177 | Log limpio: solo loguea cambios de estado.   |
| `$ErrorActionPreference`     | install_task.ps1 4        | Fail fast si algo sale mal.                          |
| `$PSScriptRoot`              | install_task.ps1 7        | Rutas relativas al script, no al CWD.                |
| Idempotencia (if-unregister) | install_task.ps1 35–37    | Se puede correr el instalador varias veces.          |
| `| Out-Null`                 | install_task.ps1 45       | Suprime ruido en consola.                            |
