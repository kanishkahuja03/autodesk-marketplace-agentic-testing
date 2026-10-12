# inputs/

One folder per plug-in. Drop the files in as they are; no particular names or format are required.

| What | Formats | Required |
|---|---|---|
| Product description (pasted from the Marketplace page) | `.txt` | Yes |
| Third-party documents (user guide, readme, release notes, …), any number | `.txt`, `.md`, `.pdf`, `.docx`, `.html` | No |
| Installer, exactly one | `.msi`, `.exe`, `.zip` (containing a `.bundle`) | Yes |
| Marketplace metadata | `metadata.json` | No (future) |

Example:
```
inputs/pid-connector-exporter/
├─ description.txt
├─ PID_Exporter_User_Guide.pdf
└─ PIDConnectorExporter.msi
```
