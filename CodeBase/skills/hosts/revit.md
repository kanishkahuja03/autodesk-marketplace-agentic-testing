---
name: revit
description: Host profile for Autodesk Revit. The facts code needs to find, start and recognise the host (host_process), and its navigation file for Agent 2.
releases:  # host version <-> release number used in plug-in manifests (minimum/maximum release)
  '2022': R2022
  '2023': R2023
  '2024': R2024
  '2025': R2025
  '2026': R2026
  '2027': R2027
host_process:
  locate:
    registry_root: 'HKLM:\SOFTWARE\Autodesk\Revit'
    value: InstallationLocation
    match_value: ProductName
    match: '^Autodesk Revit \d{4}$'
  executable: Revit.exe
  args: [/language, ENG]
  processes: [Revit.exe]
  main_window: '^Autodesk Revit \d{4}.* - \['  # '... - [Home]' or '... - [<file> - <view>]'; not the splash
  new_document: 'Project\d+'
navigation: navigation/revit-navigation.md  # host-only navigation guidance for Agent 2
navigation_steps: navigation/revit-navigation-steps.md  # the same, as steps for the find-by-name UI tools
---

# Host: Autodesk Revit (`host_id: revit`)

An Autodesk product. The `host_process` block above is read by code.
