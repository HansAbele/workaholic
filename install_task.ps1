# Registers the "Workaholic" scheduled task so workaholic.pyw starts at logon.
# Run once from an elevated PowerShell: powershell -ExecutionPolicy Bypass -File .\install_task.ps1

$ErrorActionPreference = "Stop"

$TaskName    = "Workaholic"
$ScriptPath  = Join-Path $PSScriptRoot "workaholic.pyw"

if (-not (Test-Path $ScriptPath)) {
    throw "workaholic.pyw not found at $ScriptPath"
}

# Resolve pythonw.exe (GUI Python — no console window).
$PythonwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if (-not $PythonwCmd) {
    throw "pythonw.exe not found on PATH. Install Python and ensure it is on PATH."
}
$Pythonw = $PythonwCmd.Source

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Keeps the workstation active during work hours so DeskTime does not register idle gaps." | Out-Null

Write-Host "Scheduled task '$TaskName' registered. It will run at next logon." -ForegroundColor Green
Write-Host "To start it now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "To stop it:        Stop-ScheduledTask  -TaskName $TaskName"
Write-Host "To remove it:      Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
