# Installing CUORE in a shop

## Requirements

- Windows 10 or 11, one PC that stays at the car.
- Python 3.11 or later, installed from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH"). The installer stops and tells you if it is missing; it downloads nothing itself.
- Internet for the first install only (pip fetches the packages in `requirements.txt`).
- A USB OBD adapter (see "Adapter" below).
- The release folder (or zip) from the CUORE team: it contains `release.json` and `installer\install-cuore.ps1`.

## Install

1. Unzip the release somewhere temporary (for example the Desktop).
2. Open PowerShell in the unzipped folder and preview the steps:

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File installer\install-cuore.ps1 -DryRun
   ```

3. Run it for real (Administrator PowerShell, because the default folder is under Program Files):

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File installer\install-cuore.ps1
   ```

Options: `-InstallDir D:\CUORE`, `-StateDir D:\cuore-data` (a custom state folder needs one sign-out and sign-in), `-SkipAdmin`, `-NoStart`.

The installer verifies every file against `release.json`, copies the release to `%ProgramFiles%\CUORE`, builds a private Python environment, creates the state folder (`C:\ProgramData\cuore`, where all your cars, jobs and settings live), writes a random web token to `web_token.txt` there, adds the desktop and Start Menu shortcuts and the "CUORE Server" scheduled task, starts CUORE and checks `http://127.0.0.1:5000/api/health`.

Running it again is a repair. It never deletes the state folder and keeps an existing web token.

## First admin

If the release includes the accounts module, the installer runs `python -m cuore.accounts create-admin` and asks for a name and password. Otherwise it says so and skips it; run the same command later from `%ProgramFiles%\CUORE`:

```
.venv\Scripts\python.exe -m cuore.accounts create-admin
```

## Adapter

Plug in the adapter and follow `docs/hardware/BUDGET_SETUP.md` (which adapter and bypass cable, the port and baud, and the first listen-only check). Port and baud can be seen on the Settings page.

## Update

Put the new release folder where the PC can reach it (a USB stick, a network share or a web address) and set it as the source in `C:\ProgramData\cuore\update_source.json`:

```
{"source": "E:\\cuore-0.2.0"}
```

The About page (`/about`) shows the installed version and, for a folder source, whether a newer version is available. For a web address it only looks when you press "Check now". To apply:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "%ProgramFiles%\CUORE\installer\update-cuore.ps1"
```

(`-Check` only reports.) Every file is verified against the source's `release.json` first; if one does not match, nothing changes. The state folder and the Python environment are never touched. CUORE is restarted afterwards.

## Roll back

The previous version is kept after each update:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "%ProgramFiles%\CUORE\installer\update-cuore.ps1" -Rollback
```

## Uninstall (keeping your data)

1. Remove the scheduled task: `install-cuore-autostart.ps1 -Remove` (in the install folder).
2. Delete the desktop shortcut and the Start Menu folder "CUORE".
3. Delete `%ProgramFiles%\CUORE`.
4. Leave `C:\ProgramData\cuore` alone: it holds the cars, jobs and tokens. Back it up (`scripts\backup-cuore-state.ps1`) before reinstalling on another PC, then copy it to the same place.
