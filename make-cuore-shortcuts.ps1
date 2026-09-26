# Rebuilds every shortcut that launches cuore: the desktop "CUORE Bench" link
# and the Start Menu folder "CUORE" (one link per main page). Run it again
# after adding a page. All links go through start-cuore.ps1.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File make-cuore-shortcuts.ps1

$repo = $PSScriptRoot
$vin = "ZASFAKPN5J7B88115"
$ps = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$icon = "$repo\.venv\Scripts\python.exe,0"
$dir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\CUORE"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$sh = New-Object -ComObject WScript.Shell

function New-CuoreLink([string]$path, [string]$page, [string]$desc, [switch]$Restart) {
    $l = $sh.CreateShortcut($path)
    $l.TargetPath = $ps
    $l.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$repo\start-cuore.ps1`" -Page `"$page`"" +
                   $(if ($Restart) { " -Restart" } else { "" })
    $l.WorkingDirectory = $repo
    $l.IconLocation = $icon
    $l.Description = $desc
    $l.Save()
}

$links = [ordered]@{
    "CUORE Home"                 = @("/", "All vehicles")
    "Stelvio - Dossier"          = @("/v/$vin", "Stelvio overview, codes and evidence")
    "Stelvio - Gauges"           = @("/v/$vin/gauges", "Live data gauges")
    "Stelvio - Gauges HUD"       = @("/v/$vin/gauges/hud", "Full-screen gauges")
    "Stelvio - Dashboard"        = @("/v/$vin/dashboard", "Charts and tables")
    "Stelvio - Service Hub"      = @("/v/$vin/service-hub", "All service areas")
    "Stelvio - Oil Change"       = @("/v/$vin/oil-change", "Oil change record")
    "Stelvio - Maintenance"      = @("/v/$vin/maintenance", "Routine maintenance and due items")
    "Stelvio - Brakes and Tyres" = @("/v/$vin/brakes-tires", "Brakes, wheels and tyres")
    "Stelvio - Drivetrain"       = @("/v/$vin/drivetrain/transmission", "Transmission and drivetrain")
    "Stelvio - Torque"           = @("/v/$vin/torque", "Torque settings")
    "Stelvio - Labels"           = @("/v/$vin/labels", "Print Avery service labels")
    "Stelvio - Notes"            = @("/v/$vin/notes", "Mechanic notes")
    "Stelvio - Fault Tree"       = @("/v/$vin/tree", "EVAP fault tree")
    "CUORE Live Link"            = @("/live", "Adapter, buses and live reads")
}
foreach ($k in $links.Keys) { New-CuoreLink (Join-Path $dir "$k.lnk") $links[$k][0] $links[$k][1] }
New-CuoreLink (Join-Path $dir "CUORE (restart server).lnk") "/" "Restart cuore, then open home" -Restart
New-CuoreLink "$env:USERPROFILE\Desktop\CUORE Bench.lnk" "/" "Start cuore and open the home page"

"Shortcuts written to $dir and the desktop."
