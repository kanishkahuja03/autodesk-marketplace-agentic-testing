---
name: autocad-plant3d
description: Host profile for AutoCAD Plant 3D, an AutoCAD-based Autodesk product. Only the facts code needs to find, start and recognise the host (host_process).
releases:  # host version <-> release number used in plug-in manifests (minimum/maximum release)
  '2024': R24.3
  '2025': R25.0
  '2026': R25.1
  '2027': R26.0
host_process:
  locate:
    registry_root: 'HKLM:\SOFTWARE\Autodesk\AutoCAD'
    value: AcadLocation
    match_value: ProductName
    match: '^AutoCAD Plant 3D \d{4}'
  executable: acad.exe
  args: [/product, PLNT3D, /language, en-US]
  processes: [acad.exe]
  main_window: '^(Autodesk )?AutoCAD Plant 3D \d{4}'
  new_document: 'Drawing\d+(\.dwg)?'
---

# Host: AutoCAD Plant 3D (`host_id: autocad-plant3d`)

An AutoCAD-based Autodesk product. The `host_process` block above is read by code.
