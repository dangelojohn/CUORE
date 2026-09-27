# Installs (or with -Remove, removes) the scheduled task "CUORE Server",
# which runs cuore-keepalive.ps1 at logon and re-checks every 5 minutes, so
# cuore is always available on this PC without network or Claude.
# Per-user task: no administrator rights needed.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-cuore-autostart.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-cuore-autostart.ps1 -Remove

param([switch]$Remove)

$TaskName = "CUORE Server"
$Repo = $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    "Removed scheduled task '$TaskName'."
    exit 0
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Repo\cuore-keepalive.ps1`"" `
    -WorkingDirectory $Repo

$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
# re-launch the keep-alive every 5 minutes if it ever stopped (the mutex makes
# extra launches exit at once)
$every5 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atLogon, $every5) `
    -Settings $settings -Principal $principal `
    -Description "Keeps cuore (http://127.0.0.1:5000) running. Offline; no network or Claude needed." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
"Installed and started scheduled task '$TaskName'."
