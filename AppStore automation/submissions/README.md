# Simulated marketplace submissions (PoC)

Each folder represents one **new App Store submission** event.

## Layout

```text
submissions/<submission_id>/
  metadata.json
  package/          # installer files
  docs/             # publisher documentation
```

## metadata.json (minimal)

```json
{
  "submission_id": "plant3d-plugin-001",
  "host_product": "Plant3D",
  "host_versions": ["2025"],
  "name": "Example Plugin",
  "publisher": "Example Publisher",
  "package_type": "msi"
}
```

Trigger a run (when orchestrator exists):

```bash
python -m orchestrator start --submission plant3d-plugin-001
```
