Stelvio MES backup - 2026-09-13 (before EU paddle-neutral Proxi mod)

INCLUDED
  logs/                 all 97 MES session logs (FESLog_*, SCAN_*) copied from C:\Program Files (x86)\Multiecuscan
  mes_config/           FES_Tags.ini, FES_Templates.ini, Report1.pdf,
                        multiecuscan_registry_settings.reg (only an 'installed' flag - MES does NOT keep its
                        interface/COM settings in the registry)
  BEFORE_SNAPSHOT_2026-09-13.txt   module-by-module record + restore instructions
  SHA256SUMS.txt        checksums of every file above

NOT YET INCLUDED (must be captured in MES while connected - nothing on disk holds it)
  PROXI_ORIGINAL        full Proxi hex dump from the Ctrl+Alt+C window (screenshot + copied text)
  MES_SETTINGS          screenshot of MES Settings/Interface screen (interface type, COM port, speed) -
                        not found anywhere on disk, so record it by screenshot

NOT BACKED UP BY DESIGN
  C:\Program Files (x86)\Multiecuscan\Files\ (78 MB MES program database - restored by reinstalling MES)
  Module software/firmware - MES cannot read or back up module flash; only the Proxi config changes here.

To restore MES settings: re-enter them from the MES_SETTINGS screenshot.
To undo the mod: byte 156 back to 50, run PROXI ALIGNMENT PROCEDURE.
