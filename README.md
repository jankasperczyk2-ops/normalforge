# NormalForge for Blender

One-click bevel + custom normals workflow for Nanite-ready meshes.

Copyright (C) 2024 3DC Jan Kasperczyk

## What It Does

NormalForge automates the bevel-to-custom-normals workflow, built primarily for Nanite pipelines in Unreal Engine. Nanite handles polycount but not shading — you still need clean custom normals for smooth light transitions across hard edges. NormalForge sets those up in one click.

The add-on:
1. Detects edges (by angle, bevel weights, or existing geometry)
2. Converts them to bevel weights
3. Adds and applies a bevel modifier
4. Fixes corner ngons into clean quads
5. Selects only the original faces using material tagging
6. Sets custom normals from faces on the selected areas
7. Cleans up all temporary materials

Every workflow backs up your mesh before making changes. The bevel modifier gets applied and your mesh changes, but you can restore the original at any time.

## Workflows

- **Auto-Detect by Angle** — Finds sharp edges by angle threshold, adds bevel, applies, sets normals
- **From Bevel Weights** — Uses existing bevel weight data (falls back to angle detection if none found)
- **From Existing Bevel Modifier** — Works with a bevel modifier already on your object
- **From Existing Geometry** — Detects bevel faces by area on already-beveled meshes, sets normals without adding geometry

## Bevel Settings

Full control over: width, segments, profile, affect type, width type, clamp overlap, loop slide, mark seam/sharp, outer/inner miter patterns, spread, intersection method, and face strength mode. All tucked into a collapsible panel.

## Restore System

- **Restore Original Mesh** — Reverts to the pre-bevel mesh backup
- **Clear Custom Normals Only** — Removes custom normals without changing geometry
- **Saved Backups panel** — Shows all objects with backups for individual restore

## Installation

1. Download `normalforge.zip` from the releases or Blender Hive
2. In Blender: Edit > Preferences > Add-ons > Install
3. Select the downloaded zip and enable the add-on
4. Find the panel in View3D > Sidebar (N) > NormalForge tab

## Requirements

- Blender 4.0+

## License

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See [LICENSE.txt](normalforge/LICENSE.txt) for the full license text.
