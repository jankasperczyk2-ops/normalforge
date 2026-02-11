bl_info = {
    "name": "NormalForge",
    "author": "Your Name",
    "version": (3, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > NormalForge",
    "description": "One-click bevel + custom normals workflow for game-ready meshes",
    "category": "Mesh",
}

import bpy
import bmesh
import uuid
import math
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, IntProperty, EnumProperty, BoolProperty

NF_BACKUP_KEY = "nf_backup_mesh"
DEFAULT_ANGLE = 0.523599


class NF_Properties(PropertyGroup):
    bevel_width: FloatProperty(
        name="Width",
        description="Width of the bevel",
        default=0.02,
        min=0.0001,
        max=100.0,
        step=1,
        precision=4,
    )

    bevel_segments: IntProperty(
        name="Segments",
        description="Number of bevel segments",
        default=1,
        min=1,
        max=100,
    )

    bevel_profile: FloatProperty(
        name="Profile",
        description="Profile shape (0.5 = round)",
        default=0.5,
        min=0.0,
        max=1.0,
        step=1,
        precision=2,
    )

    bevel_affect: EnumProperty(
        name="Affect",
        description="What geometry to bevel",
        items=[
            ('EDGES', "Edges", "Bevel edges"),
            ('VERTICES', "Vertices", "Bevel vertices"),
        ],
        default='EDGES',
    )

    bevel_offset_type: EnumProperty(
        name="Width Type",
        description="Method for determining bevel width",
        items=[
            ('OFFSET', "Offset", "Amount is offset of new edges from original"),
            ('WIDTH', "Width", "Amount is width of new faces"),
            ('DEPTH', "Depth", "Amount is perpendicular distance from original edge to bevel face"),
            ('PERCENT', "Percent", "Amount is percent of adjacent edge length"),
            ('ABSOLUTE', "Absolute", "Amount is absolute distance along adjacent edge"),
        ],
        default='OFFSET',
    )

    bevel_clamp_overlap: BoolProperty(
        name="Clamp Overlap",
        description="Clamp the width to avoid overlap",
        default=False,
    )

    bevel_loop_slide: BoolProperty(
        name="Loop Slide",
        description="Prefer sliding along edges to having even widths",
        default=True,
    )

    bevel_mark_seam: BoolProperty(
        name="Mark Seam",
        description="Mark seam edges on bevel faces",
        default=False,
    )

    bevel_mark_sharp: BoolProperty(
        name="Mark Sharp",
        description="Mark sharp edges on bevel faces",
        default=False,
    )

    bevel_miter_outer: EnumProperty(
        name="Outer Miter",
        description="Pattern to use for outside of miters",
        items=[
            ('MITER_SHARP', "Sharp", "Outside of miter is sharp"),
            ('MITER_PATCH', "Patch", "Outside of miter is a patch"),
            ('MITER_ARC', "Arc", "Outside of miter is an arc"),
        ],
        default='MITER_SHARP',
    )

    bevel_miter_inner: EnumProperty(
        name="Inner Miter",
        description="Pattern to use for inside of miters",
        items=[
            ('MITER_SHARP', "Sharp", "Inside of miter is sharp"),
            ('MITER_ARC', "Arc", "Inside of miter is an arc"),
        ],
        default='MITER_SHARP',
    )

    bevel_spread: FloatProperty(
        name="Spread",
        description="Amount to spread arcs for inner miters",
        default=0.1,
        min=0.0,
        max=1.0,
        step=1,
        precision=3,
    )

    bevel_vmesh_method: EnumProperty(
        name="Intersection Method",
        description="Method for handling vertex mesh intersections",
        items=[
            ('ADJ', "Grid Fill", "Default grid fill method"),
            ('CUTOFF', "Cutoff", "Cut off faces at intersection"),
        ],
        default='ADJ',
    )

    bevel_face_strength_mode: EnumProperty(
        name="Face Strength",
        description="Whether to set face strength and which faces to set it on",
        items=[
            ('FSTR_NONE', "None", "Do not set face strength"),
            ('FSTR_NEW', "New", "Set face strength on new faces only"),
            ('FSTR_AFFECTED', "Affected", "Set face strength on new and affected faces"),
            ('FSTR_ALL', "All", "Set face strength on all faces"),
        ],
        default='FSTR_NONE',
    )

    auto_sharp_angle: FloatProperty(
        name="Sharp Angle",
        description="Angle threshold for auto-detecting sharp edges",
        default=0.523599,
        min=0.0,
        max=3.14159,
        subtype='ANGLE',
    )

    detect_ratio: FloatProperty(
        name="Detection Ratio",
        description="Faces with area below this ratio of the median area are considered bevel faces",
        default=0.5,
        min=0.01,
        max=1.0,
        step=1,
        precision=2,
    )

    show_bevel_options: BoolProperty(
        name="Bevel Options",
        description="Show or hide bevel modifier settings",
        default=False,
    )


def ensure_object_mode(context):
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def ensure_edit_mode(context):
    if context.object and context.object.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')


def get_bevel_weight_layer(bm):
    layer = bm.edges.layers.float.get("bevel_weight_edge")
    if layer is None:
        layer = bm.edges.layers.float.new("bevel_weight_edge")
    return layer


def edges_by_angle(bm, angle_threshold):
    layer = get_bevel_weight_layer(bm)
    count = 0
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            face_angle = edge.link_faces[0].normal.angle(edge.link_faces[1].normal)
            if face_angle > angle_threshold:
                edge[layer] = 1.0
                count += 1
        elif len(edge.link_faces) == 1:
            edge[layer] = 1.0
            count += 1
    return count


def prepare_bevel_weights(obj, source, angle_threshold=DEFAULT_ANGLE):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = get_bevel_weight_layer(bm)

    count = 0

    if source == 'BEVEL_WEIGHT':
        for edge in bm.edges:
            if edge[layer] > 0.0:
                count += 1
        if count == 0:
            count = edges_by_angle(bm, angle_threshold)

    elif source == 'ANGLE':
        for edge in bm.edges:
            edge[layer] = 0.0
        count = edges_by_angle(bm, angle_threshold)

    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()

    return count


def create_unique_tag_material(obj):
    if len(obj.data.materials) == 0:
        default_mat = bpy.data.materials.new(name="_NF_Default")
        obj.data.materials.append(default_mat)

    tag_name = "_NF_Tag_" + uuid.uuid4().hex[:8]
    mat = bpy.data.materials.new(name=tag_name)
    mat.diffuse_color = (1.0, 0.0, 1.0, 0.5)
    mat.use_fake_user = False
    obj.data.materials.append(mat)
    tag_slot_index = len(obj.material_slots) - 1
    return tag_slot_index, tag_name


def cleanup_tag_material(obj, tag_name):
    tag_index = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material and slot.material.name == tag_name:
            tag_index = i
            break

    if tag_index is not None:
        ensure_object_mode(bpy.context)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for face in bm.faces:
            if face.material_index == tag_index:
                face.material_index = 0
            elif face.material_index > tag_index:
                face.material_index -= 1
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        obj.active_material_index = tag_index
        bpy.ops.object.material_slot_remove()

    mat = bpy.data.materials.get(tag_name)
    if mat:
        bpy.data.materials.remove(mat)

    default_mat_index = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material and slot.material.name == "_NF_Default":
            default_mat_index = i
            break

    if default_mat_index is not None:
        default_mat = bpy.data.materials.get("_NF_Default")
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for face in bm.faces:
            if face.material_index == default_mat_index:
                face.material_index = 0
            elif face.material_index > default_mat_index:
                face.material_index -= 1
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        obj.active_material_index = default_mat_index
        bpy.ops.object.material_slot_remove()

        if default_mat:
            bpy.data.materials.remove(default_mat)


def add_bevel_modifier(obj, props, tag_material_index):
    bevel_mod = obj.modifiers.new(name="NF_Bevel", type='BEVEL')
    bevel_mod.limit_method = 'WEIGHT'
    bevel_mod.width = props.bevel_width
    bevel_mod.segments = props.bevel_segments
    bevel_mod.profile = props.bevel_profile
    bevel_mod.affect = props.bevel_affect
    bevel_mod.offset_type = props.bevel_offset_type
    bevel_mod.use_clamp_overlap = props.bevel_clamp_overlap
    bevel_mod.loop_slide = props.bevel_loop_slide
    bevel_mod.mark_seam = props.bevel_mark_seam
    bevel_mod.mark_sharp = props.bevel_mark_sharp
    bevel_mod.miter_outer = props.bevel_miter_outer
    bevel_mod.miter_inner = props.bevel_miter_inner
    bevel_mod.spread = props.bevel_spread
    bevel_mod.vmesh_method = props.bevel_vmesh_method
    bevel_mod.face_strength_mode = props.bevel_face_strength_mode
    bevel_mod.harden_normals = False
    bevel_mod.material = tag_material_index
    return bevel_mod


def select_original_faces_by_material(obj, tag_material_index):
    ensure_edit_mode(bpy.context)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False

    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    selected = 0
    for face in bm.faces:
        if face.material_index != tag_material_index:
            face.select = True
            selected += 1

    bmesh.update_edit_mesh(obj.data)
    return selected


def ensure_smooth_shading(obj):
    ensure_object_mode(bpy.context)
    mesh = obj.data

    for poly in mesh.polygons:
        poly.use_smooth = True

    if hasattr(mesh, 'use_auto_smooth'):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = 3.14159


def set_normals_from_faces(context):
    ensure_edit_mode(context)
    try:
        bpy.ops.mesh.set_normals_from_faces()
    except Exception:
        pass


def create_mesh_backup(obj):
    old_backup_name = obj.get(NF_BACKUP_KEY)
    if old_backup_name:
        old_mesh = bpy.data.meshes.get(old_backup_name)
        if old_mesh:
            bpy.data.meshes.remove(old_mesh)

    backup_mesh = obj.data.copy()
    backup_name = ".nf_backup_" + uuid.uuid4().hex[:8]
    backup_mesh.name = backup_name
    backup_mesh.use_fake_user = True

    obj[NF_BACKUP_KEY] = backup_name


def has_backup(obj):
    backup_name = obj.get(NF_BACKUP_KEY)
    if not backup_name:
        return False
    return bpy.data.meshes.get(backup_name) is not None


def restore_mesh_backup(obj):
    backup_name = obj.get(NF_BACKUP_KEY)
    if not backup_name:
        return False

    backup_mesh = bpy.data.meshes.get(backup_name)
    if backup_mesh is None:
        return False

    current_mesh = obj.data
    restored_mesh = backup_mesh.copy()
    restored_mesh.name = current_mesh.name

    obj.data = restored_mesh

    bpy.data.meshes.remove(current_mesh)

    bpy.data.meshes.remove(backup_mesh)
    if NF_BACKUP_KEY in obj:
        del obj[NF_BACKUP_KEY]

    return True


def fix_bevel_ngons(obj, tag_material_index):
    ensure_edit_mode(bpy.context)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False

    ngon_count = 0
    for face in bm.faces:
        if face.material_index == tag_material_index and len(face.verts) > 4:
            face.select = True
            ngon_count += 1

    bmesh.update_edit_mesh(obj.data)

    if ngon_count > 0:
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
        bpy.ops.mesh.tris_convert_to_quads(
            face_threshold=0.698132,
            shape_threshold=0.698132,
        )

    return ngon_count


def run_workflow(obj, props):
    ensure_smooth_shading(obj)

    tag_index, tag_name = create_unique_tag_material(obj)

    bevel_mod = add_bevel_modifier(obj, props, tag_index)

    bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

    fix_bevel_ngons(obj, tag_index)

    selected = select_original_faces_by_material(obj, tag_index)

    set_normals_from_faces(bpy.context)

    ensure_object_mode(bpy.context)

    cleanup_tag_material(obj, tag_name)

    return selected


class NF_OT_from_bevel_weight(Operator):
    """Use existing bevel weights, add bevel, apply, and set custom normals. Falls back to angle detection if no weights exist."""
    bl_idname = "object.nf_from_bevel_weight"
    bl_label = "From Bevel Weights"
    bl_description = "Use existing bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.nf_props

        ensure_object_mode(context)

        count = prepare_bevel_weights(obj, 'BEVEL_WEIGHT', props.auto_sharp_angle)
        if count == 0:
            self.report({'WARNING'}, "No edges found to process")
            return {'CANCELLED'}

        create_mesh_backup(obj)
        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Processed {count} edges")
        return {'FINISHED'}


class NF_OT_from_auto_sharp(Operator):
    """Auto-detect edges by angle threshold, convert to bevel weights, add bevel, apply, and set custom normals"""
    bl_idname = "object.nf_from_auto_sharp"
    bl_label = "Auto-Detect by Angle"
    bl_description = "Auto-detect edges by angle, convert to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.nf_props

        ensure_object_mode(context)

        count = prepare_bevel_weights(obj, 'ANGLE', props.auto_sharp_angle)
        if count == 0:
            self.report({'WARNING'}, "No edges detected above the angle threshold")
            return {'CANCELLED'}

        create_mesh_backup(obj)
        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Processed {count} edges")
        return {'FINISHED'}


class NF_OT_from_existing_bevel(Operator):
    """Apply existing bevel modifier and set custom normals"""
    bl_idname = "object.nf_from_existing_bevel"
    bl_label = "From Existing Bevel Modifier"
    bl_description = "Apply an existing bevel modifier and set custom normals on original faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is None or obj.type != 'MESH' or obj.mode != 'OBJECT':
            return False
        return any(mod.type == 'BEVEL' for mod in obj.modifiers)

    def execute(self, context):
        obj = context.object

        ensure_object_mode(context)
        create_mesh_backup(obj)

        bevel_mod = None
        for mod in obj.modifiers:
            if mod.type == 'BEVEL':
                bevel_mod = mod
                break

        if bevel_mod is None:
            self.report({'WARNING'}, "No bevel modifier found")
            return {'CANCELLED'}

        ensure_smooth_shading(obj)

        tag_index, tag_name = create_unique_tag_material(obj)
        bevel_mod.material = tag_index

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces_by_material(obj, tag_index)
        set_normals_from_faces(bpy.context)
        ensure_object_mode(bpy.context)
        cleanup_tag_material(obj, tag_name)

        self.report({'INFO'}, "Done! Applied existing bevel and set custom normals")
        return {'FINISHED'}


def detect_bevel_faces(obj, ratio_threshold):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    if len(bm.faces) < 2:
        bm.free()
        return (0, set())

    areas = sorted([f.calc_area() for f in bm.faces])
    median_area = areas[len(areas) // 2]

    if median_area <= 0:
        bm.free()
        return (0, set())

    cutoff = median_area * ratio_threshold

    small_faces = set()
    large_faces = set()
    for face in bm.faces:
        if face.calc_area() < cutoff:
            small_faces.add(face.index)
        else:
            large_faces.add(face.index)

    if not small_faces or not large_faces:
        bm.free()
        return (0, set())

    neighbors = {}
    for face in bm.faces:
        adj = set()
        for edge in face.edges:
            for linked in edge.link_faces:
                if linked.index != face.index:
                    adj.add(linked.index)
        neighbors[face.index] = adj

    confirmed_bevel = set()
    frontier = set()
    for idx in large_faces:
        for n in neighbors[idx]:
            if n in small_faces:
                frontier.add(n)

    while frontier:
        current = frontier.pop()
        if current in confirmed_bevel:
            continue
        confirmed_bevel.add(current)
        for n in neighbors[current]:
            if n in small_faces and n not in confirmed_bevel:
                frontier.add(n)

    original_indices = large_faces.copy()
    for idx in small_faces:
        if idx not in confirmed_bevel:
            original_indices.add(idx)

    bm.free()
    return len(confirmed_bevel), original_indices


def select_faces_by_indices(obj, face_indices):
    ensure_edit_mode(bpy.context)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False

    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    selected = 0
    for face in bm.faces:
        if face.index in face_indices:
            face.select = True
            selected += 1

    bmesh.update_edit_mesh(obj.data)
    return selected


class NF_OT_from_geometry(Operator):
    """Detect bevel faces on already-beveled geometry by face area and set custom normals on the original larger faces"""
    bl_idname = "object.nf_from_geometry"
    bl_label = "From Existing Geometry"
    bl_description = "Auto-detect bevel faces by size and set custom normals on the original faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.nf_props

        ensure_object_mode(context)

        result = detect_bevel_faces(obj, props.detect_ratio)
        bevel_count, original_indices = result

        if bevel_count == 0:
            self.report({'WARNING'}, "No bevel faces detected — try adjusting the detection ratio")
            return {'CANCELLED'}

        if len(original_indices) == 0:
            self.report({'WARNING'}, "No original faces found — all faces appear to be bevel geometry")
            return {'CANCELLED'}

        create_mesh_backup(obj)
        ensure_smooth_shading(obj)

        select_faces_by_indices(obj, original_indices)
        set_normals_from_faces(bpy.context)
        ensure_object_mode(bpy.context)

        self.report({'INFO'}, f"Done! Detected {bevel_count} bevel faces, set normals on {len(original_indices)} original faces")
        return {'FINISHED'}


class NF_OT_restore_by_name(Operator):
    """Restore a specific object's backup mesh"""
    bl_idname = "object.nf_restore_by_name"
    bl_label = "Restore"
    bl_description = "Restore this object's original mesh from backup"
    bl_options = {'REGISTER', 'UNDO'}

    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj_name)
        if obj is None:
            self.report({'WARNING'}, f"Object '{self.obj_name}' not found")
            return {'CANCELLED'}

        old_active = context.view_layer.objects.active
        context.view_layer.objects.active = obj

        ensure_object_mode(context)

        if restore_mesh_backup(obj):
            self.report({'INFO'}, f"Restored original mesh for '{self.obj_name}'")
        else:
            self.report({'WARNING'}, f"No backup found for '{self.obj_name}'")
            context.view_layer.objects.active = old_active
            return {'CANCELLED'}

        context.view_layer.objects.active = old_active
        return {'FINISHED'}


class NF_OT_remove(Operator):
    """Remove custom normals and restore original mesh"""
    bl_idname = "object.nf_remove"
    bl_label = "Remove NormalForge"
    bl_description = "Restore original mesh from backup, removing bevel geometry and custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is None or obj.type != 'MESH' or obj.mode != 'OBJECT':
            return False
        return has_backup(obj)

    def execute(self, context):
        obj = context.object

        ensure_object_mode(context)

        if restore_mesh_backup(obj):
            self.report({'INFO'}, "Restored original mesh")
        else:
            self.report({'WARNING'}, "No backup found to restore")
            return {'CANCELLED'}

        return {'FINISHED'}


class NF_OT_clear_normals(Operator):
    """Clear custom normals without restoring geometry"""
    bl_idname = "object.nf_clear_normals"
    bl_label = "Clear Custom Normals"
    bl_description = "Remove custom split normals from the mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is None or obj.type != 'MESH' or obj.mode != 'OBJECT':
            return False
        return obj.data.has_custom_normals

    def execute(self, context):
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        self.report({'INFO'}, "Cleared custom normals")
        return {'FINISHED'}


class NF_PT_main_panel(Panel):
    bl_label = "NormalForge"
    bl_idname = "NF_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NormalForge'

    def draw(self, context):
        layout = self.layout
        props = context.scene.nf_props
        obj = context.object

        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return

        box = layout.box()
        row = box.row(align=True)
        row.prop(props, "show_bevel_options",
                 icon='TRIA_DOWN' if props.show_bevel_options else 'TRIA_RIGHT',
                 emboss=False)

        if props.show_bevel_options:
            col = box.column(align=True)
            col.prop(props, "bevel_width")
            col.prop(props, "bevel_segments")
            col.prop(props, "bevel_profile", slider=True)

            col.separator()
            col.prop(props, "bevel_affect")
            col.prop(props, "bevel_offset_type")

            col.separator()
            row = col.row(align=True)
            row.prop(props, "bevel_clamp_overlap")
            row = col.row(align=True)
            row.prop(props, "bevel_loop_slide")

            col.separator()
            row = col.row(align=True)
            row.prop(props, "bevel_mark_seam")
            row = col.row(align=True)
            row.prop(props, "bevel_mark_sharp")

            col.separator()
            col.prop(props, "bevel_miter_outer")
            col.prop(props, "bevel_miter_inner")
            if props.bevel_miter_inner == 'MITER_ARC':
                col.prop(props, "bevel_spread")

            col.separator()
            col.prop(props, "bevel_vmesh_method")
            col.prop(props, "bevel_face_strength_mode")

        layout.separator()

        box = layout.box()
        box.label(text="Workflows", icon='PLAY')

        col = box.column(align=True)
        col.scale_y = 1.3

        col.operator("object.nf_from_auto_sharp", icon='LIGHT_HEMI')
        col.prop(props, "auto_sharp_angle")

        col.separator()
        col.operator("object.nf_from_bevel_weight", icon='MOD_BEVEL')

        has_bevel_mod = any(mod.type == 'BEVEL' for mod in obj.modifiers)
        if has_bevel_mod:
            col.separator()
            col.operator("object.nf_from_existing_bevel", icon='CHECKMARK')

        col.separator()
        col.operator("object.nf_from_geometry", icon='MESH_DATA')
        col.prop(props, "detect_ratio")

        layout.separator()

        box = layout.box()
        box.label(text="Toggle / Restore", icon='FILE_REFRESH')
        col = box.column(align=True)
        col.scale_y = 1.3

        backup_exists = has_backup(obj)
        row = col.row(align=True)
        row.enabled = backup_exists
        row.operator("object.nf_remove", icon='LOOP_BACK', text="Restore Original Mesh")

        col.separator()

        row = col.row(align=True)
        row.enabled = obj.data.has_custom_normals
        row.operator("object.nf_clear_normals", icon='X', text="Clear Custom Normals Only")

        if backup_exists:
            col.label(text="Backup available", icon='CHECKMARK')
        else:
            col.label(text="No backup (run a workflow first)", icon='INFO')

        layout.separator()

        backed_up_objects = []
        for o in bpy.data.objects:
            if o.type == 'MESH' and has_backup(o):
                backed_up_objects.append(o)

        box = layout.box()
        box.label(text="Saved Backups", icon='FILE_BACKUP')
        if backed_up_objects:
            for o in backed_up_objects:
                row = box.row(align=True)
                icon = 'OUTLINER_OB_MESH'
                row.label(text=o.name, icon=icon)
                op = row.operator("object.nf_restore_by_name", text="", icon='LOOP_BACK')
                op.obj_name = o.name
        else:
            box.label(text="No backups saved", icon='INFO')

        layout.separator()

        box = layout.box()
        box.label(text="Mesh Info", icon='INFO')
        mesh = obj.data
        col = box.column(align=True)
        col.label(text=f"Vertices: {len(mesh.vertices)}")
        col.label(text=f"Polygons: {len(mesh.polygons)}")
        col.label(text=f"Custom Normals: {'Yes' if mesh.has_custom_normals else 'No'}")

        sharp_count = sum(1 for e in mesh.edges if e.use_edge_sharp)
        seam_count = sum(1 for e in mesh.edges if e.use_seam)
        col.label(text=f"Sharp Edges: {sharp_count}")
        col.label(text=f"Seam Edges: {seam_count}")

        if obj.modifiers:
            box = layout.box()
            box.label(text="Modifiers", icon='MODIFIER')
            for mod in obj.modifiers:
                row = box.row()
                icon = 'MOD_BEVEL' if mod.type == 'BEVEL' else 'DOT'
                row.label(text=mod.name, icon=icon)


classes = (
    NF_Properties,
    NF_OT_from_bevel_weight,
    NF_OT_from_auto_sharp,
    NF_OT_from_existing_bevel,
    NF_OT_from_geometry,
    NF_OT_restore_by_name,
    NF_OT_remove,
    NF_OT_clear_normals,
    NF_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nf_props = bpy.props.PointerProperty(type=NF_Properties)


def unregister():
    del bpy.types.Scene.nf_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
