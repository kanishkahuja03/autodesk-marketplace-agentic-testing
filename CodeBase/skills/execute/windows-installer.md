---
name: windows-installer
description: How Agent 2 installs and uninstalls an app on Windows (silently, with msiexec) and reads the results, using only the allowed Windows-MCP tools and PowerShell commands. Used by Agent 2 only.
---

# Windows installer testing (Agent 2)

You carry out test steps on this Windows machine through the Windows-MCP tools. You **report raw values**; code decides PASS/FAIL. The process is already elevated (admin). There is no UAC prompt to handle.

## 1. Allowed PowerShell commands
The PowerShell tool only accepts commands that **start with** one of these; anything else is rejected:
- `Start-Process -FilePath msiexec.exe …` (the silent install and the silent uninstall below)
- `Get-AuthenticodeSignature …`
- `Get-ItemProperty …`, `Get-ChildItem …`, `Test-Path …`
- `Select-String …` (search a file, e.g. a msiexec log)
- `Get-CimInstance Win32_OperatingSystem …`
- `([Security.Principal.WindowsPrincipal]…` (admin check)

Use the **Registry** and **FileSystem** tools for reads. Both are **read-only** for you: you never write, copy, move or delete files. Your results go only through `record_observation`.

**Reading files:** never read a whole log or other large file with FileSystem `read` (the guardrail rejects files over 50 KB without `limit`). Use `Select-String -Path "<file>" -Pattern "<text>"` to find the lines you need, or FileSystem `read` with `offset` and `limit`. Tool results longer than 20,000 characters are cut off. PowerShell's CLIXML noise is removed for you; error messages are shown as "(PowerShell error output)".

## 2. Silent install (INST)
```powershell
Start-Process -FilePath msiexec.exe -ArgumentList '/i','"<INSTALLER_PATH>"','/qn','/norestart','/l*v','"<RUN_DIR>\evidence\install.log"' -Wait
```
- Use `-Wait`: without it, msiexec returns before the install has finished. The `evidence` folder already exists.
- Don't add `-PassThru | Select-Object -ExpandProperty ExitCode`: inside this tool it always fails with "Process must exit before requested information can be determined", even when the install worked.
- **Run the install only once.** Running it again would test something else (a repair or a second install), and the guardrail rejects a second `/i`. Whatever PowerShell printed, don't reinstall: read the result from the log.
- **Then always read the real result from the log** with `Select-String` (never with FileSystem `read`: msiexec logs are large UTF-16 files):
  ```powershell
  Select-String -Path "<RUN_DIR>\evidence\install.log" -Pattern "success or error status", "MainEngineThread is returning"
  ```
  The number after `error status:` (or after `is returning`) is the msiexec exit code. Report **that** number as `install_exit_code`.
- The PowerShell tool's own `Status Code` is **not** msiexec's exit code. Never report it as `install_exit_code`.
- If there is no log or no result line, report `install_exit_code: null` and say why in `notes`. Never guess a value.
- Report `evidence/install.log` as evidence only if the file exists (record_observation rejects missing files).
- Exit codes: `0` success · `3010` success, restart needed · `1602` cancelled · `1603` fatal error · `1605` product not installed · `1618` another install is running · `1638` another version is already installed. Report the code; don't interpret it.
- Use a tool timeout long enough for the installer (e.g. `timeout` 300).

## 3. Silent uninstall (UNIN)
Uninstall the same way, silently, using the **ProductCode** from your input ("App under test"):
```powershell
Start-Process -FilePath msiexec.exe -ArgumentList '/x','<ProductCode>','/qn','/norestart','/l*v','"<RUN_DIR>\evidence\uninstall.log"' -Wait
```
- Run it **once**, then read the result from the log:
  ```powershell
  Select-String -Path "<RUN_DIR>\evidence\uninstall.log" -Pattern "success or error status", "MainEngineThread is returning"
  ```
  Report that number as `uninstall_exit_code` (same codes as above), and `evidence/uninstall.log` as evidence.
- **Afterwards** check the Uninstall entry (section 4) and the installed files (section 5) again for the UNIN tests. Don't reuse results from before the uninstall.

## 4. Programs and Features (Uninstall) entry
Your input lists the exact registry paths to check ("App under test"). Check them **after** the install for INST tests and **after** the uninstall for UNIN tests. Look in all three places, by ProductCode first, then by DisplayName:
- `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`
- `HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`
- `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`

Registry tool `mode="list"` (or `mode="get"` with a value `name`) with these paths. Report `uninstall_entry_exists` (true/false), and when found also `display_name`, `display_version`, `publisher`, `install_location` if a test observes them. Report which path it was found under in `notes`.

## 5. Files and folders
FileSystem `mode="info"` or `"list"` (or `Test-Path`). Use the real folder paths given in your input (e.g. `%APPDATA%`); never guess user names or profile paths. Report `true`/`false` for `*_exists` keys.

## 6. Signature
```powershell
Get-AuthenticodeSignature -FilePath "<INSTALLER_PATH>" | Format-List Status, StatusMessage, SignerCertificate
```
Report `signature_status` (e.g. `Valid`, `NotSigned`, `HashMismatch`) and `signer_subject` (the `[Subject]` line of the certificate, e.g. `CN=…, O=…`).

The guardrail rejects `;`, `{ }` (except GUIDs), `$( )`, `&` outside quotes, redirection and line breaks, and allows pipes only into `Select-Object`, `Format-List`, `Format-Table`, `Sort-Object`, `Measure-Object`, `Out-String` or `ConvertTo-Json`. Keep commands to one line. Names that contain `&` (e.g. `P&ID`) are fine inside quotes.

## 7. UI rules (whenever a step needs the screen)
- Start programs only with the App tool and a **full path**. **Never use Win+R / the Run dialog** or the Start menu search.
- **Never click or type at guessed coordinates.** Call `Snapshot` first and use the element `label` it gives.
- **Never click, type into or close the console window** titled `…cmd.exe` or `…python…`: it's the test pipeline itself.
- If the same action failed twice, stop trying it: record what you saw (`executed: false`) and move on.

## 8. Resolving placeholders (during ENV)
Fill every `${NAME}` from `required_env` with a real value found on this machine, using read-only checks only (registry values such as `AcadLocation` or `InstallLocation`, the folders given in your input, the installer facts). Return them in your final output `env`. If you can't resolve one, leave it out and say why in the notes of the test that needed it.
