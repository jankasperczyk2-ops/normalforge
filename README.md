# Auto Custom Normals for Blender

A Blender add-on that provides one-click bevel + custom normals workflows for game-ready meshes. Automatically converts sharp edges, seams, or bevel weights into proper custom normals with a toggleable system.

## The Problem

In game development, getting clean custom normals from bevels requires a multi-step manual process: marking edges, adding a bevel modifier, applying it, selecting the right faces, and setting normals. This is tedious and error-prone.

## The Solution

Auto Custom Normals automates the entire pipeline in a single click:
1. Detects edges (sharp, seams, bevel weights, or auto-detect by angle)
2. Converts them to bevel weights
3. Marks seams at the same locations
4. Adds a bevel modifier using those weights
5. Applies the bevel
6. Selects only the original flat faces (not the new bevel geometry) using material tagging
7. Sets custom normals from face on those selected areas

Plus a **Restore** button lets you go back to the original mesh at any time.

## Workflows

- **From Sharp Edges** - Uses existing sharp edge markings
- **From Seams** - Uses existing UV seam markings
- **From Bevel Weights** - Uses existing bevel weight data
- **Auto-Detect Sharp** - Detects sharp edges by angle threshold (for meshes with no markings)
- **From Existing Bevel Modifier** - Works with a bevel modifier you already set up

## Settings

- **Bevel Width** - Control the bevel size before running
- **Bevel Segments** - Number of bevel segments
- **Auto Sharp Angle** - Angle threshold for auto-detection mode

## Toggle System

- **Restore Original Mesh** - Reverts to the pre-bevel mesh (backup created automatically)
- **Clear Custom Normals Only** - Removes custom normals without changing geometry

## Installation

1. Download \`auto_custom_normals.py\`
2. In Blender: Edit > Preferences > Add-ons > Install
3. Select the downloaded file and enable the add-on
4. Find the panel in View3D > Sidebar (N) > Auto Custom Normals tab

## Requirements

- Blender 4.0+

## License

MIT License
