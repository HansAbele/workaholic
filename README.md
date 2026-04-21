# Workaholic

Daemon ligero para Windows que mantiene la máquina principal activa durante el
horario laboral, evitando que DeskTime registre periodos "idle" cuando estás
trabajando desde otro equipo.

---

## 1. ¿Qué hace?

Cada ~4 minutos, durante tu horario laboral, mueve el cursor del mouse 1 pixel
a la derecha y lo regresa a su posición original. Este "nudge" es
imperceptible visualmente, pero el sistema operativo lo registra como evento
de input válido, y DeskTime lo cuenta como actividad.

Además, mientras estás en horario laboral, **le pide a Windows que no se
duerma ni suspenda** (keep-awake), porque si el equipo entra en reposo el
proceso se congela y aparecería un gap en DeskTime igual que antes.

Fuera del horario laboral el proceso sigue vivo pero no hace nada (modo
**guard**), se **libera el keep-awake** para que el equipo pueda dormir
normalmente, y no aparecen eventos sospechosos a las 3 AM ni durante tu hora
de almuerzo.

---

## 2. Cómo funciona

### 2.1 Heartbeat (latido)
- **Mecanismo**: `pyautogui.moveRel(1, 0, duration=0.1)` seguido de
  `pyautogui.moveRel(-1, 0, duration=0.1)`.
- **Por qué mouse y no teclado**: una pulsación de teclado podría
  introducir caracteres si estás escribiendo en otra ventana. El cursor solo
  se mueve 1 px, ida y vuelta, así que nunca interfiere.
- **Intervalo**: 240 s (4 min) con jitter aleatorio de ±15 s. El umbral de
  idle por defecto de DeskTime es 5 min, así que 4 min da margen de
  seguridad. El jitter evita un patrón perfectamente mecánico.

### 2.2 Ventana de horario
El programa solo emite heartbeats cuando se cumplen **todas** estas
condiciones:

| Condición        | Valor                           |
|------------------|---------------------------------|
| Día de la semana | Lunes a viernes                 |
| Hora             | 09:00 – 18:00                   |
| Excepción        | Pausa 13:00 – 14:00 (almuerzo)  |

Fuera de esa ventana el loop duerme 60 s y vuelve a chequear.

### 2.3 Logging
- Archivo: `%USERPROFILE%\workaholic.log` (p. ej.
  `C:\Users\USER\workaholic.log`).
- Rotación: archivos de hasta 1 MB, conserva 3 copias (`workaholic.log`,
  `workaholic.log.1`, …).
- Formato: `YYYY-MM-DD HH:MM:SS [NIVEL] mensaje`.
- Excepciones fatales se capturan con `try/except` y se escriben con
  traceback completo antes de que el proceso muera.

### 2.4 Ejecución invisible
El script se llama `workaholic.pyw`. Windows asocia la extensión `.pyw` con
`pythonw.exe` (Python sin consola), por lo que corre en segundo plano sin
ventana.

### 2.5 Autoarranque
No usamos la carpeta *Startup* ni el registro de Windows. Usamos el
**Programador de Tareas** porque permite:
- Reintentar si el proceso falla (3 reintentos con 1 min de espera).
- Correr tanto con batería como con corriente.
- Arrancar automáticamente si el equipo estaba apagado en el momento del
  trigger (`StartWhenAvailable`).
- Una sola instancia a la vez (`MultipleInstances IgnoreNew`).

### 2.6 Keep-awake (evitar reposo/suspensión)
Si el equipo se duerme, el proceso se congela y no puede enviar heartbeats,
así que aparecería un gap en DeskTime igual que antes. Para evitarlo, cuando
entramos a la ventana laboral llamamos a la API de Windows
**`SetThreadExecutionState`** (vía `ctypes`) con los flags:

| Flag                 | Efecto                                            |
|----------------------|---------------------------------------------------|
| `ES_CONTINUOUS`      | El flag persiste hasta que lo cambiemos.          |
| `ES_SYSTEM_REQUIRED` | El sistema no entra en reposo mientras esté puesto. |

- Al **entrar** a la ventana laboral → se activa el flag (el equipo no
  duerme).
- Al **salir** (almuerzo, fin de jornada, fin de semana) → se libera el flag
  (el equipo puede dormir normalmente como siempre).
- Al **terminar** el proceso → hay un `try/finally` que libera el flag,
  incluso ante una excepción fatal.

Notas:
- **No afecta la pantalla**: solo evita que el sistema se suspenda. El
  monitor puede apagarse/atenuarse igual. Si quisieras mantener la pantalla
  también, habría que sumar el flag `ES_DISPLAY_REQUIRED`.
- **No requiere admin**: cualquier proceso puede pedirlo para sí mismo.
- **Se limita al horario**: fuera de la ventana laboral el equipo se duerme
  como cualquier máquina normal, ahorrando batería.

---

## 3. Archivos del proyecto

| Archivo               | Propósito                                                   |
|-----------------------|-------------------------------------------------------------|
| `workaholic.pyw`      | Script principal. Corre el loop de heartbeat + guard.       |
| `install_task.ps1`    | Registra la tarea programada `Workaholic` en Windows.       |
| `requirements.txt`    | Dependencias de Python (pyautogui).                         |
| `README.md`           | Este documento.                                             |
| `CODE_WALKTHROUGH.md` | Explicación línea por línea del código (educativo).         |
| `LICENSE`             | Licencia MIT.                                               |

---

## 4. Requisitos previos

- **Windows 10 / 11**.
- **Python 3.x** instalado y en el `PATH` (debe resolverse `pythonw.exe`).
  Verifica con:
  ```powershell
  Get-Command pythonw.exe
  ```
- **Privilegios de administrador** para registrar la tarea programada.

---

## 5. Instalación

Abre **PowerShell como Administrador** y ejecuta, en este orden:

```powershell
# 1. Ir a la carpeta del proyecto
cd C:\Users\USER\Documents\PX\WORKFORCE\workaholic

# 2. Instalar la dependencia Python
pip install -r requirements.txt

# 3. Registrar la tarea programada
powershell -ExecutionPolicy Bypass -File .\install_task.ps1

# 4. Arrancar ahora (sin esperar al próximo logon)
Start-ScheduledTask -TaskName Workaholic
```

Tras el paso 3 verás en verde:
`Scheduled task 'Workaholic' registered. It will run at next logon.`

---

## 6. Verificación

Sigue el log en vivo:

```powershell
Get-Content $env:USERPROFILE\workaholic.log -Wait -Tail 20
```

Dentro de los primeros 4 minutos (en horario laboral) deberías ver:

```
2026-04-21 09:05:12 [INFO] Workaholic started (pid=12345, log=C:\Users\USER\workaholic.log)
2026-04-21 09:05:12 [INFO] Entering work window — heartbeat active; keep-awake ON.
2026-04-21 09:09:07 [INFO] Heartbeat sent (cursor nudge).
2026-04-21 09:13:04 [INFO] Heartbeat sent (cursor nudge).
```

A las 13:00: `Outside work window — entering guard mode; keep-awake OFF.`
A las 14:00: `Entering work window — heartbeat active; keep-awake ON.`

Usa `Ctrl+C` para salir del `tail`.

---

## 7. Operaciones comunes

```powershell
# Ver estado de la tarea
Get-ScheduledTask -TaskName Workaholic | Select TaskName, State

# Arrancar manualmente
Start-ScheduledTask -TaskName Workaholic

# Parar el proceso en curso (no desinstala la tarea)
Stop-ScheduledTask -TaskName Workaholic

# Ver las últimas 50 líneas del log
Get-Content $env:USERPROFILE\workaholic.log -Tail 50
```

---

## 8. Configuración (tunning)

Todos los parámetros ajustables están como constantes al inicio de
`workaholic.pyw`:

| Constante                     | Default | Descripción                                   |
|-------------------------------|---------|-----------------------------------------------|
| `HEARTBEAT_INTERVAL_SECONDS`  | 240     | Intervalo base entre heartbeats (s).          |
| `HEARTBEAT_JITTER_SECONDS`    | 15      | Variación aleatoria ± (s).                    |
| `MOUSE_NUDGE_PIXELS`          | 1       | Pixels que se mueve el cursor.                |
| `MOUSE_MOVE_DURATION`         | 0.1     | Duración de cada transición (s).              |
| `WORK_DAYS`                   | Mon–Fri | Set de días laborables (Mon=0).               |
| `WORK_START` / `WORK_END`     | 09–18   | Ventana de trabajo.                           |
| `LUNCH_START` / `LUNCH_END`   | 13–14   | Pausa de almuerzo.                            |
| `GUARD_POLL_SECONDS`          | 60      | Frecuencia de chequeo fuera de horario.       |

Después de editar, reinicia la tarea:

```powershell
Stop-ScheduledTask  -TaskName Workaholic
Start-ScheduledTask -TaskName Workaholic
```

> **Cuidado** con subir `HEARTBEAT_INTERVAL_SECONDS` por encima de 285 s:
> el jitter positivo podría empujarlo a 300 s, que es el umbral idle de
> DeskTime.

---

## 9. Desinstalación

Abre **PowerShell como Administrador** y ejecuta:

```powershell
# 1. Parar y eliminar la tarea programada
Stop-ScheduledTask       -TaskName Workaholic -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName Workaholic -Confirm:$false

# 2. (Opcional) Borrar los archivos del proyecto
Remove-Item -Recurse -Force C:\Users\USER\Documents\PX\WORKFORCE\workaholic

# 3. (Opcional) Borrar los logs
Remove-Item $env:USERPROFILE\workaholic.log*

# 4. (Opcional) Desinstalar la dependencia Python
pip uninstall pyautogui
```

---

## 10. Troubleshooting

| Síntoma                                          | Qué revisar                                                                 |
|--------------------------------------------------|-----------------------------------------------------------------------------|
| No aparece `workaholic.log` después de arrancar  | La tarea no está corriendo: `Get-ScheduledTask -TaskName Workaholic`.       |
| Log dice `ModuleNotFoundError: pyautogui`        | Falta `pip install pyautogui` en el mismo Python que resuelve `pythonw.exe`.|
| `install_task.ps1` falla con "Access denied"     | No abriste PowerShell como Administrador.                                   |
| DeskTime sigue marcando idle                     | Revisa el intervalo; tal vez DeskTime tiene umbral < 5 min en tu org.       |
| El cursor "salta" visiblemente                   | Reduce `MOUSE_NUDGE_PIXELS` a 1 (default) y/o sube `MOUSE_MOVE_DURATION`.   |
| `Outside work window` a media jornada            | Revisa la hora del sistema y la zona horaria de Windows.                    |

Para ver el histórico de ejecuciones de la tarea:

```powershell
Get-ScheduledTaskInfo -TaskName Workaholic
```

---

## 11. Notas de diseño

- **`pyautogui.FAILSAFE = False`**: pyautogui aborta por defecto si el cursor
  toca una esquina de la pantalla. El heartbeat debe sobrevivir incluso si el
  cursor está en reposo en una esquina, por eso lo desactivamos.
- **`RotatingFileHandler`** en vez de `FileHandler`: evita que el log crezca
  indefinidamente.
- **Chequeo de ventana cada iteración** (no un sleep largo): si cambia la hora
  del sistema (p. ej. cambio de DST), el guard detecta la transición en
  menos de 60 s.
- **Keep-awake vía `SetThreadExecutionState`** en lugar de cambiar el plan de
  energía de Windows: (a) no requiere admin, (b) es automático — al morir el
  proceso, Windows vuelve al comportamiento normal; (c) se limita al horario
  laboral, así fuera de jornada la máquina ahorra energía como siempre.
- **`try/finally` alrededor del loop**: garantiza que `set_keep_awake(False)`
  siempre se llame al salir, incluso si hay una excepción fatal, evitando
  dejar al sistema en modo "no duerme" tras un crash.
