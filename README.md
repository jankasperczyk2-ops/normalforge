# NormalForge for Blender

A Blender add-on that provides one-click bevel + custom normals workflows for game-ready meshes. Automatically converts sharp edges or bevel weights into proper custom normals with a toggleable system.

## The Problem

In game development, getting clean custom normals from bevels requires a multi-step manual process: marking edges, adding a bevel modifier, applying it, selecting the right faces, and setting normals. This is tedious and error-prone.

## The Solution

NormalForge automates the entire pipeline in a single click:
1. Detects edges (bevel weights or auto-detect by angle)
2. Converts them to bevel weights
3. Adds a bevel modifier using those weights
4. Applies the bevel
5. Fixes corner n-gons into clean quads
6. Selects only the original flat faces (not the new bevel geometry) using material tagging
7. Sets custom normals from faces on those selected areas

Plus a **Restore** button lets you go back to the original mesh at any time.

## Workflows

- **Auto-Detect by Angle** - Detects sharp edges by angle threshold (for meshes with no markings)
- **From Bevel Weights** - Uses existing bevel weight data (falls back to angle detection if none found)
- **From Existing Bevel Modifier** - Works with a bevel modifier you already set up

## Bevel Settings

Full control over bevel parameters: width, segments, profile, affect type, width type, clamp overlap, loop slide, mark seam/sharp, outer/inner miter patterns, spread, intersection method, and face strength mode.

## Toggle System

- **Restore Original Mesh** - Reverts to the pre-bevel mesh (backup created automatically)
- **Clear Custom Normals Only** - Removes custom normals without changing geometry

## Installation

1. Download \`normalforge.py\`
2. In Blender: Edit > Preferences > Add-ons > Install
3. Select the downloaded file and enable the add-on
4. Find the panel in View3D > Sidebar (N) > NormalForge tab

## Requirements

- Blender 4.0+

## License

MIT License
