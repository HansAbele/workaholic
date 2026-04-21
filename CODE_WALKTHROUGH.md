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
import random
import sys
import time
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler

import pyautogui
```

- `ctypes`: permite llamar funciones de librerías nativas (DLLs en Windows,
  `.so` en Linux). Lo usamos para invocar `SetThreadExecutionState` del
  kernel de Windows y pedirle que no se duerma.
- `logging`: módulo estándar para registrar eventos en archivos / consola.
- `os`: acceso al sistema operativo (variables de entorno, rutas, PID).
- `random`: generador de números pseudoaleatorios (para el jitter).
- `sys`: acceso al intérprete (lo usamos para `sys.exit(1)` y para detectar
  la plataforma con `sys.platform`).
- `time`: funciones de tiempo; aquí solo `time.sleep()`.
- `from datetime import datetime, time as dtime`
  - Importa **dos cosas** del módulo `datetime`:
    - `datetime`: clase para fecha+hora.
    - `time`: clase para "solo hora del día" — pero como ya importamos
      arriba el **módulo** llamado `time`, renombramos con `as dtime` para
      evitar colisión de nombres.
- `from logging.handlers import RotatingFileHandler`
  - `RotatingFileHandler` no está en el módulo raíz `logging`; vive en el
    submódulo `logging.handlers`. Rota el archivo cuando supera cierto tamaño.
- Línea en blanco antes de `import pyautogui`: convención PEP 8 —
  stdlib primero, luego librerías de terceros, separadas por una línea.
- `pyautogui`: librería de terceros (requiere `pip install pyautogui`). Mueve
  mouse, simula teclado, toma screenshots.

### Bloque de constantes (líneas 16–34)

```python
# ---------------------------------------------------------------------------
# Configuration constants — tune these if schedule or behavior needs to change.
# ---------------------------------------------------------------------------
```

Comentario-banner. Solo texto para humanos; Python lo ignora.

```python
HEARTBEAT_INTERVAL_SECONDS = 240
```

- Convención PEP 8: **MAYÚSCULAS_CON_GUIONES_BAJOS** = constante.
- Python **no** tiene verdaderas constantes (podrías reasignarla), pero la
  convención le avisa al lector "no tocar en runtime".
- 240 s = 4 min. Por debajo del umbral idle de DeskTime (5 min).

```python
HEARTBEAT_JITTER_SECONDS = 15
```

Rango del ruido aleatorio que se suma/resta al intervalo base.

```python
MOUSE_NUDGE_PIXELS = 1
MOUSE_MOVE_DURATION = 0.1
```

Cuánto se mueve y en cuánto tiempo. `0.1` es float (segundos).

```python
WORK_DAYS = {0, 1, 2, 3, 4}
```

- Llaves `{...}` con elementos sueltos = **set** (conjunto). No hay duplicados
  y la pertenencia (`x in WORK_DAYS`) es O(1).
- Los enteros corresponden al método `datetime.weekday()`: Lunes=0, Martes=1,
  …, Domingo=6. Así que este set representa Mon–Fri.

```python
WORK_START = dtime(9, 0)
WORK_END = dtime(18, 0)
LUNCH_START = dtime(13, 0)
LUNCH_END = dtime(14, 0)
```

- `dtime(9, 0)` crea un objeto `datetime.time` con hora=9, minuto=0. Es "solo
  hora del día", sin fecha.
- Los objetos `time` se pueden comparar con `<`, `<=`, etc. — por eso podemos
  hacer `WORK_START <= current < WORK_END` más abajo.

```python
GUARD_POLL_SECONDS = 60
```

Cuánto duerme el loop cuando está fuera de horario. Un minuto da buena
reactividad sin consumir CPU.

```python
LOG_FILENAME = "workaholic.log"
LOG_PATH = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), LOG_FILENAME)
```

- `os.environ.get("USERPROFILE", fallback)` — lee la variable de entorno
  `USERPROFILE` (en Windows = `C:\Users\USER`). Si no existiera (por ejemplo,
  en Linux/Mac), usa `os.path.expanduser("~")` como respaldo, que resuelve a
  la carpeta home del usuario.
- `os.path.join(a, b)` concatena con el separador correcto de cada OS (`\`
  en Windows, `/` en Unix). Nunca concatenes rutas con `+` directamente.

### Setup de logging (líneas 36–46)

```python
logger = logging.getLogger("workaholic")
```

- `getLogger("nombre")` devuelve un **logger con nombre**. Si ya existe uno
  con ese nombre, devuelve el mismo (singleton por nombre). Usar un nombre
  evita interferir con el logger raíz.

```python
logger.setLevel(logging.INFO)
```

- Umbral: ignora mensajes por debajo de INFO (DEBUG). La jerarquía es
  `DEBUG < INFO < WARNING < ERROR < CRITICAL`.

```python
_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
```

- El guión bajo `_handler` es convención: "variable privada, no pensada para
  uso externo". Python no lo hace privado de verdad, es señal al lector.
- `maxBytes=1_000_000` — el guion bajo en el número es un **separador de
  miles** (Python 3.6+). Puramente visual. Equivale a `1000000`.
- `backupCount=3` — cuando llega a 1 MB, rota: `workaholic.log` →
  `workaholic.log.1`, y los viejos se desplazan (`.1` → `.2`, `.2` → `.3`,
  `.3` se descarta).
- `encoding="utf-8"` — evita problemas con caracteres no-ASCII en Windows
  (por defecto usaría `cp1252` y podría petar con tildes/emojis).

```python
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
```

- `Formatter` define cómo se renderiza cada registro.
- Los `%(name)s` son placeholders de `logging`: `asctime` = timestamp,
  `levelname` = "INFO"/"ERROR"/etc., `message` = el texto que pasaste.
- `datefmt` usa códigos de `strftime`: `%Y` año 4 dígitos, `%m` mes,
  `%d` día, etc.

```python
logger.addHandler(_handler)
```

Conecta el handler al logger. Sin esto, los `logger.info(...)` no van a
ninguna parte.

### Desactivar el fail-safe de pyautogui (líneas 48–50)

```python
# Disable pyautogui's fail-safe (corner-hit abort) since nudges are tiny and
# the script must survive a cursor that happens to rest in a screen corner.
pyautogui.FAILSAFE = False
```

- Por defecto, pyautogui **lanza una excepción** si el mouse toca una esquina
  de la pantalla (mecanismo de "pánico" para que puedas matar un script
  descontrolado moviendo el cursor a la esquina).
- Nuestro heartbeat debe sobrevivir aunque el cursor esté descansando en una
  esquina, así que desactivamos esta salvaguarda.

### Keep-awake — `set_keep_awake` (líneas 52–66)

```python
ES_CONTINUOUS = 0x80000000        # Flag persists until changed
ES_SYSTEM_REQUIRED = 0x00000001   # Prevent system sleep (display can still dim)
```

- Estas son **constantes de Win32** (valores exactos que espera la API de
  Windows). Las definimos nosotros porque Python no las trae de fábrica.
- `0x80000000` y `0x00000001` son literales hexadecimales. Se combinan con
  OR bit a bit (`|`) para pasarle varios flags juntos.
- La documentación oficial de Microsoft lista más flags
  (`ES_DISPLAY_REQUIRED`, `ES_AWAYMODE_REQUIRED`, etc.) pero aquí solo nos
  interesa "no te duermas, sistema".

```python
def set_keep_awake(enabled: bool) -> None:
    """Tell Windows to stay awake while enabled; release the request when not."""
    if sys.platform != "win32":
        return
```

- `sys.platform` devuelve `"win32"` en Windows (sí, incluso 64-bit), `"linux"`
  en Linux, `"darwin"` en macOS. Como la API que vamos a llamar solo existe
  en Windows, hacemos un early-return en otras plataformas para que el
  script siga siendo "portable-ish": funcionará en Linux/Mac, simplemente sin
  keep-awake.

```python
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if enabled else ES_CONTINUOUS
```

- **Expresión condicional** (ternario en Python): `A if cond else B`.
  - Si `enabled=True` → `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` ("no te duermas,
    y deja este flag puesto").
  - Si `enabled=False` → solo `ES_CONTINUOUS` ("olvida la petición de no
    dormir, vuelve al comportamiento normal, pero sigue respetando flags
    futuros que te diga").
- Esta es **la forma idiomática** de liberar el keep-awake en Windows:
  llamar con solo `ES_CONTINUOUS` quita los flags previos.

```python
    if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0:
        logger.warning("SetThreadExecutionState returned 0 (call failed).")
```

- `ctypes.windll.kernel32` accede a `kernel32.dll`, la DLL más básica de
  Windows (la que expone funciones como `CreateFile`, `Sleep`,
  `GetTickCount`, etc.).
- `SetThreadExecutionState(flags)` devuelve el estado anterior si funcionó,
  o `0` si falló. Por eso chequeamos el retorno y logueamos warning si es 0.
- **No requiere privilegios de administrador**: cualquier proceso puede
  pedir que el sistema no se duerma *mientras ese proceso viva*. Al morir el
  proceso, Windows descarta automáticamente la petición.

### Función `is_within_work_window` (líneas 69–78)

```python
def is_within_work_window(now: datetime) -> bool:
    """True only during Mon–Fri work hours, excluding the lunch hour."""
```

- `now: datetime` — **anotación de tipo**. Python no lo chequea en runtime
  (salvo que uses herramientas como mypy), pero documenta la intención.
- `-> bool` — tipo de retorno.
- Docstring de función.

```python
    if now.weekday() not in WORK_DAYS:
        return False
```

- `weekday()` devuelve un int 0–6.
- `not in` usa el operador de pertenencia contra el set. Si no es día hábil,
  corta ya.

```python
    current = now.time()
```

Extrae solo la parte "hora del día" del datetime (sin la fecha). Devuelve un
`datetime.time`, comparable con nuestras constantes.

```python
    if not (WORK_START <= current < WORK_END):
        return False
```

- Encadenamiento de comparaciones: equivale a
  `(WORK_START <= current) and (current < WORK_END)`.
- `<` en `WORK_END` (y no `<=`) significa que 18:00:00 en punto **sí** corta
  el horario. Si fuera `<=`, a las 18:00:00.000 aún saldría un heartbeat.

```python
    if LUNCH_START <= current < LUNCH_END:
        return False
```

Mismo patrón pero invertido: si está dentro del almuerzo, no es ventana
laboral.

```python
    return True
```

Pasó todos los filtros → sí es ventana laboral.

### Función `nudge_mouse` (líneas 81–84)

```python
def nudge_mouse() -> None:
    """Move the cursor 1 px right and back with a smooth transition."""
    pyautogui.moveRel(MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
    pyautogui.moveRel(-MOUSE_NUDGE_PIXELS, 0, duration=MOUSE_MOVE_DURATION)
```

- `moveRel(dx, dy, duration=s)` mueve **relativo** a la posición actual.
  - `dx=+1, dy=0` → 1 px a la derecha.
  - `dx=-1, dy=0` → 1 px a la izquierda (vuelve al origen).
- `duration=0.1` hace que pyautogui interpole el movimiento en 0.1 s (en
  lugar de un salto instantáneo). Genera varios eventos de mouse en vez de
  uno solo, lo que se ve más "humano" para sistemas de detección de bots.
- `-> None` declara explícitamente que no devuelve nada.

### Función `next_heartbeat_delay` (líneas 87–89)

```python
def next_heartbeat_delay() -> float:
    jitter = random.uniform(-HEARTBEAT_JITTER_SECONDS, HEARTBEAT_JITTER_SECONDS)
    return HEARTBEAT_INTERVAL_SECONDS + jitter
```

- `random.uniform(a, b)` devuelve un float uniforme en `[a, b]`. Con -15 y
  +15, el resultado final estará entre 225 s y 255 s.
- Se extrajo a función propia para que sea fácil de testear y entender.

### Función `run` — el loop principal (líneas 92–119)

```python
def run() -> None:
    logger.info("Workaholic started (pid=%s, log=%s)", os.getpid(), LOG_PATH)
```

- `logger.info(format, *args)` — pasarle los argumentos separados (en lugar
  de hacer `f"pid={os.getpid()}"`) es más eficiente: si el nivel INFO
  estuviera deshabilitado, `logging` no gastaría tiempo formateando el
  mensaje.
- `os.getpid()` devuelve el Process ID. Útil para debug.

```python
    in_work_window_prev = None
```

- Guardamos el estado anterior para detectar **transiciones** (entrar o
  salir de la ventana laboral) y logearlas.
- `None` significa "aún no sabemos", así que la primera iteración siempre
  loguea el estado inicial (porque `True != None` o `False != None`).

```python
    try:
        while True:
```

- Envolvemos el loop en `try ... finally` para garantizar cleanup del
  keep-awake aunque haya una excepción o KeyboardInterrupt (ver el `finally`
  al final de la función).
- `while True` = loop infinito. Solo se sale por excepción, KeyboardInterrupt
  o fin del proceso.

```python
            now = datetime.now()
            in_work_window = is_within_work_window(now)
```

Capturamos la hora actual **una sola vez** por iteración y reusamos.

```python
            if in_work_window != in_work_window_prev:
                set_keep_awake(in_work_window)
                if in_work_window:
                    logger.info("Entering work window — heartbeat active; keep-awake ON.")
                else:
                    logger.info("Outside work window — entering guard mode; keep-awake OFF.")
                in_work_window_prev = in_work_window
```

- Solo actúa cuando **cambia** el estado.
- `set_keep_awake(in_work_window)` aplica el flag correcto en la transición:
  al entrar a horario laboral activa el keep-awake; al salir lo libera.
- Solo loguea en transiciones. Si siempre logueáramos, el archivo se llenaría
  de "Outside work window" cada 60 s durante la noche.
- Actualizar `in_work_window_prev` **después** del log.

```python
            if in_work_window:
                try:
                    nudge_mouse()
                    logger.info("Heartbeat sent (cursor nudge).")
                except Exception as exc:
                    logger.exception("Heartbeat failed: %s", exc)
                time.sleep(next_heartbeat_delay())
            else:
                time.sleep(GUARD_POLL_SECONDS)
```

- `try/except Exception` — captura cualquier fallo de pyautogui (por ejemplo,
  si la sesión está bloqueada) sin matar el loop.
- `logger.exception(...)` loguea el mensaje **más el traceback** (lo que te
  permite diagnosticar después). Es como `logger.error(..., exc_info=True)`.
- El `sleep` está **fuera** del try/except, así que si `sleep` fuera
  interrumpido (no lo es en uso normal), también caería.
- Rama `else`: estamos en guard mode, dormimos 60 s y volvemos a chequear.

```python
    finally:
        set_keep_awake(False)
```

- El `finally` **siempre** se ejecuta al salir del `try`, pase lo que pase:
  retorno normal, excepción capturada arriba, KeyboardInterrupt, o una
  excepción no capturada que sube al caller.
- Garantiza liberar el flag de keep-awake antes de que el proceso muera.
  Si no hiciéramos esto y el proceso crashara, Windows igual liberaría el
  flag (porque el proceso terminó), pero el `finally` deja el mensaje
  explícito en el log y hace visible la intención en el código.

### Bloque principal (líneas 122–129)

```python
if __name__ == "__main__":
```

- **Idioma Python clásico**: `__name__` es `"__main__"` cuando el archivo se
  ejecuta directamente, y el nombre del módulo cuando se importa. Este
  guardián permite que el archivo se pueda importar sin ejecutar `run()`
  automáticamente (útil para tests).

```python
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Workaholic stopped by user (KeyboardInterrupt).")
```

Ctrl+C se loguea como parada limpia (no es un error).

```python
    except Exception as exc:
        logger.critical("Fatal error — Workaholic is terminating: %s", exc, exc_info=True)
        sys.exit(1)
```

- Cualquier otra excepción no capturada dentro de `run()` cae aquí. La
  logueamos como **CRITICAL** con traceback completo (`exc_info=True`).
- `sys.exit(1)` termina el proceso con código 1 (= error). El Programador
  de Tareas verá ese código y aplicará la política de reintento.

---

## Parte 2 — `install_task.ps1`

### Comentarios iniciales (líneas 1–2)

```powershell
# Registers the "Workaholic" scheduled task so workaholic.pyw starts at logon.
# Run once from an elevated PowerShell: powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```

En PowerShell, `#` inicia un comentario de una línea. Solo para humanos.

### Modo estricto de errores (línea 4)

```powershell
$ErrorActionPreference = "Stop"
```

- Variable automática de PowerShell. Por defecto vale `"Continue"`, que hace
  que los errores **no terminales** se impriman pero el script siga.
- Con `"Stop"`, cualquier error se convierte en terminante y aborta el
  script. Evita dejar una instalación a medias.

### Variables de configuración (líneas 6–7)

```powershell
$TaskName    = "Workaholic"
$ScriptPath  = Join-Path $PSScriptRoot "workaholic.pyw"
```

- `$Variable` — todas las variables en PowerShell llevan `$`.
- `$PSScriptRoot` es una variable automática: la carpeta donde vive el
  script `.ps1`. No depende de desde dónde lo ejecutes. Usar esto en vez de
  `Get-Location` asegura que encontramos el `.pyw` aunque corras el
  instalador desde otro directorio.
- `Join-Path a b` es el equivalente PowerShell de `os.path.join`.

### Validación de que el script existe (líneas 9–11)

```powershell
if (-not (Test-Path $ScriptPath)) {
    throw "workaholic.pyw not found at $ScriptPath"
}
```

- `Test-Path` devuelve `$true`/`$false` si la ruta existe.
- `-not` es el operador de negación lógica.
- `throw "mensaje"` lanza una excepción; combinado con `$ErrorActionPreference
  = "Stop"`, detiene el script con un error claro.

### Resolver `pythonw.exe` (líneas 13–18)

```powershell
# Resolve pythonw.exe (GUI Python — no console window).
$PythonwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
```

- `Get-Command` busca un ejecutable en el `PATH` (similar a `which` en
  Unix).
- `-ErrorAction SilentlyContinue` — si no lo encuentra, no revienta; devuelve
  `$null`. Así podemos darle un mensaje de error más amigable.

```powershell
if (-not $PythonwCmd) {
    throw "pythonw.exe not found on PATH. Install Python and ensure it is on PATH."
}
$Pythonw = $PythonwCmd.Source
```

- `-not $PythonwCmd` es true si la variable es `$null`, string vacía, 0, etc.
- `.Source` es la propiedad con la ruta absoluta al ejecutable (p.ej.
  `C:\Python314\pythonw.exe`).

### Definir la acción (línea 20)

```powershell
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$ScriptPath`""
```

- `New-ScheduledTaskAction` arma un objeto que representa "qué ejecutar".
- `-Execute` = ruta del programa.
- `-Argument` = argumentos como string.
- **`` `" ``** es la forma de escapar una comilla doble dentro de un string
  entre comillas dobles. Necesitamos envolver `$ScriptPath` en comillas
  porque si la ruta tuviera espacios, Windows podría cortarla. El resultado
  final pasado al ejecutable es algo como:
  `"C:\Users\USER\...\workaholic.pyw"` (con comillas literales).

### Definir el trigger (línea 22)

```powershell
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
```

- `-AtLogOn` = arrancar al iniciar sesión.
- `$env:USERNAME` — manera de leer variables de entorno en PowerShell.
  Equivalente a `os.environ["USERNAME"]` en Python.
- Así la tarea solo arranca cuando **tú** inicias sesión, no cuando otro
  usuario lo hace.

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

- El acento grave **`` ` ``** al final de cada línea es el **continuador de
  línea** de PowerShell (como `\` en bash). Sin él, PowerShell consideraría
  terminada la instrucción al final de la primera línea.
- `-AllowStartIfOnBatteries` — por defecto Windows no arranca tareas
  programadas en batería. Lo habilitamos.
- `-DontStopIfGoingOnBatteries` — si ya está corriendo y pasas a batería,
  que no la mate.
- `-StartWhenAvailable` — si el equipo estaba apagado a la hora del trigger,
  arrancar en cuanto se encienda.
- `-RestartCount 3` + `-RestartInterval 1min` — si la tarea falla, reintenta
  hasta 3 veces, esperando 1 min entre intentos.
- `-ExecutionTimeLimit (New-TimeSpan -Days 0)` — `0` significa **sin
  límite**. Por defecto una tarea se mata a las 72 h. Como este es un daemon,
  lo queremos eterno.
- `-MultipleInstances IgnoreNew` — si ya hay una instancia corriendo y
  llega otro trigger (no debería, pero por si acaso), ignora la nueva.

### Definir el principal (línea 33)

```powershell
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
```

- `-UserId` = quién ejecuta la tarea.
- `-LogonType Interactive` = requiere que el usuario haya hecho logon
  interactivo (como es tu caso, con sesión abierta). Si pusieras
  `ServiceAccountLogonType`, correría como servicio incluso sin logon.
- `-RunLevel Limited` = con permisos normales, **no** elevados. Moverse el
  mouse no requiere admin, y es mejor correr con el mínimo privilegio.

### Limpieza si la tarea ya existe (líneas 35–37)

```powershell
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
```

- Si ya hay una tarea con ese nombre (por una instalación previa), la
  eliminamos primero. Así el script es **idempotente**: lo puedes correr
  múltiples veces sin errores.
- `-Confirm:$false` — evita el prompt interactivo "¿seguro?".

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

- Ensambla todos los objetos que preparamos arriba.
- `| Out-Null` envía la salida al "agujero negro". Sin esto, PowerShell
  imprimiría el objeto `ScheduledTask` resultante en pantalla, que es ruido.

### Mensajes al usuario (líneas 47–50)

```powershell
Write-Host "Scheduled task '$TaskName' registered. It will run at next logon." -ForegroundColor Green
Write-Host "To start it now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "To stop it:        Stop-ScheduledTask  -TaskName $TaskName"
Write-Host "To remove it:      Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
```

- `Write-Host` imprime a la consola. `-ForegroundColor Green` tiñe el texto.
  (Nota: `Write-Host` no escribe al pipeline — si quisieras que otro script
  capturara la salida, usarías `Write-Output`.)
- Variables `$...` se expanden dentro de strings con comillas dobles.
- En la última línea, **`` `$false ``** escapa el `$` para que aparezca
  literal en el mensaje (no queremos que se expanda a su valor).

---

## Resumen de patrones que aparecen en el código

| Patrón                       | Dónde aparece             | Por qué                                              |
|------------------------------|---------------------------|------------------------------------------------------|
| Constantes al inicio         | workaholic.pyw 20–34      | Fácil de tunear sin buscar en la lógica.             |
| Guard `if __name__ == ...`   | workaholic.pyw 122        | Permite importar el módulo sin ejecutar el loop.     |
| `try/except` en loop         | workaholic.pyw 110–114    | Un nudge fallido no debe matar el daemon.            |
| `try/finally` en loop        | workaholic.pyw 96–119     | Garantiza cleanup de keep-awake al salir.            |
| `try/except` top-level       | workaholic.pyw 123–129    | Fatales quedan logueados antes de morir.             |
| Rotación de log              | workaholic.pyw 42         | Evita archivo que crece sin límite.                  |
| Jitter aleatorio             | workaholic.pyw 88         | Rompe el patrón mecánico.                            |
| Detección de transición      | workaholic.pyw 101–107    | Log limpio y aplicación de keep-awake en transición. |
| Llamada a Win32 vía `ctypes` | workaholic.pyw 60–66      | Acceso a `SetThreadExecutionState` sin libs extra.   |
| Guard por plataforma         | workaholic.pyw 62–63      | El script sigue corriendo en Linux/Mac sin petar.    |
| `$ErrorActionPreference`     | install_task.ps1 4        | Fail fast si algo sale mal.                          |
| `$PSScriptRoot`              | install_task.ps1 7        | Rutas relativas al script, no al CWD.                |
| Idempotencia (if-unregister) | install_task.ps1 35–37    | Se puede correr el instalador varias veces.          |
| `| Out-Null`                 | install_task.ps1 45       | Suprime ruido en consola.                            |
