# Non-Destructive Custom Normals for Blender

A Blender add-on that allows you to bake custom normals from an evaluated mesh without applying modifiers.

## The Problem

In game development, custom normals setups require models with applied modifiers. This is destructive to your workflow because you lose the ability to edit your modifier stack.

## The Solution

This add-on creates a non-destructive workflow by:
1. Accessing the evaluated mesh (after all modifiers)
2. Calculating custom normals on that mesh
3. Writing the normals back to the base mesh
4. Keeping your modifier stack intact

## Features

- **Bake Custom Normals** - Copy normals from evaluated mesh to base mesh
- **Weighted Normals** - Calculate weighted normals using face area, corner angle, or combined weighting
- **Clear Custom Normals** - Remove custom split normals when needed
- **Mesh Info Panel** - Shows vertex/loop/polygon counts and modifier stack

## Installation

1. Download `non_destructive_normals.py`
2. In Blender: Edit → Preferences → Add-ons → Install
3. Select the downloaded file and enable the add-on
4. Find the panel in View3D → Sidebar (N) → Normals tab

## Requirements

- Blender 4.0+

## Usage

1. Select a mesh object with modifiers
2. Open the Normals panel in the sidebar (N key)
3. Click "Bake Custom Normals" to transfer normals from the evaluated mesh
4. Export your model - custom normals will be preserved!

## License

MIT License
