---
name: windows-installer
description: How Agent 2 installs and uninstalls an app on Windows and reads the results, using only the allowed Windows-MCP tools and PowerShell commands. Used by Agent 2 only.
---

# Windows installer testing (Agent 2)

You carry out test steps on this Windows machine through the Windows-MCP tools. You **report raw values**; code decides PASS/FAIL. The process is already elevated (admin). There is no UAC prompt to handle.

## 1. Allowed PowerShell commands
The PowerShell tool only accepts commands that **start with** one of these; anything else is rejected:
- `Start-Process -FilePath msiexec.exe …` (install, and uninstall only if a step says so)
- `Get-AuthenticodeSignature …`
- `Get-ItemProperty …`, `Get-ChildItem …`, `Test-Path …`
- `Select-String …` (search a file, e.g. the install log)
- `Get-CimInstance Win32_OperatingSystem …`
- `([Security.Principal.WindowsPrincipal]…` (admin check)

Use the **Registry** and **FileSystem** tools for reads when you can. Both are read-only for you. FileSystem may write only inside the run folder you were given. Never delete anything.

## 2. Silent install (INST)
```powershell
Start-Process -FilePath msiexec.exe -ArgumentList '/i','"<INSTALLER_PATH>"','/qn','/norestart','/l*v','"<RUN_DIR>\evidence\install.log"' -Wait -PassThru | Select-Object -ExpandProperty ExitCode
```
- Use `-Wait -PassThru`: without it, msiexec returns before the install has finished. The `evidence` folder already exists.
- **Run the install only once.** Running it again would test something else (a repair or a second install).
- **Then always read the real result from the log**, even if PowerShell printed a number:
  ```powershell
  Select-String -Path "<RUN_DIR>\evidence\install.log" -Pattern "success or error status", "MainEngineThread is returning"
  ```
  The number after `error status:` (or after `is returning`) is the msiexec exit code. Report **that** number as `install_exit_code`. If it differs from what PowerShell printed, use the log's number and mention both in `notes`.
- The PowerShell tool's own `Status Code` is **not** msiexec's exit code. Never report it as `install_exit_code`.
- If there is no log or no result line, report `install_exit_code: null` and say why in `notes`. Never guess a value.
- Report `evidence/install.log` as evidence only if the file exists (record_observation rejects missing files).
- Exit codes: `0` success · `3010` success, restart needed · `1602` cancelled · `1603` fatal error · `1618` another install is running · `1638` another version is already installed. Report the code; don't interpret it.
- Use a tool timeout long enough for the installer (e.g. `timeout` 300).

## 3. Programs and Features (Uninstall) entry
Look in all three places, by ProductCode first, then by DisplayName:
- `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`
- `HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`
- `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`

Registry tool `mode="get"`/`"list"` with these PowerShell-style paths. Report `uninstall_entry_exists` (true/false), and when found also `display_name`, `display_version`, `publisher`, `install_location` if a test observes them. Report which path it was found under in `notes`.

## 4. Files and folders
FileSystem `mode="info"` or `"list"` (or `Test-Path`). Expand `%AppData%` etc. to real paths first (e.g. `Get-ChildItem Env:APPDATA`). Report `true`/`false` for `*_exists` keys.

## 5. Signature
```powershell
Get-AuthenticodeSignature -FilePath "<INSTALLER_PATH>" | Format-List Status, StatusMessage, SignerCertificate
```
Report `signature_status` (e.g. `Valid`, `NotSigned`, `HashMismatch`) and `signer_subject` (the `[Subject]` line of the certificate, e.g. `CN=…, O=…`).

The guardrail rejects `;`, `{ }` (except GUIDs), `$( )`, `&`, redirection and line breaks, and allows pipes only into `Select-Object`, `Format-List`, `Format-Table`, `Sort-Object`, `Measure-Object`, `Out-String` or `ConvertTo-Json`. Keep commands to one line.

## 6. Uninstall through the Windows UI (UNIN)
The demo uninstalls **the way a user does**, through Control Panel → Programs and Features:
1. App tool `mode="launch_executable"`, `executable="control.exe"`, `args=["appwiz.cpl"]`.
2. `WaitFor` `active_window` "Programs and Features". Then call `Snapshot` to see the list.
3. Find the app's row by its DisplayName (scroll if needed) and click it to select it. Prefer `Click` with the element `label` from the Snapshot.
4. Click **Uninstall** (toolbar button or right-click → Uninstall).
5. Confirm the dialog ("Are you sure you want to uninstall …?") with **Yes**.
6. Wait until the progress window is gone and the row disappears (`WaitFor`, or `Snapshot` again). Then take a `Screenshot`.
7. Close the Programs and Features window.
8. Then check the registry (section 3) and the files (section 4) for the UNIN tests.

If a step fails (window not found, row missing, unexpected dialog), take a `Screenshot`, describe what you saw in `notes`, record the observation with `executed: false`, and continue with the next test. **Don't** fall back to `msiexec /x` yourself: code cleans up at the end if needed.

## 7. Resolving placeholders (during ENV)
Fill every `${NAME}` from `required_env` with a real value found on this machine, using read-only checks only (registry values such as `AcadLocation` or `InstallLocation`, expanded environment variables, the installer facts). Return them in your final output `env`. If you can't resolve one, leave it out and say why in the notes of the test that needed it.
