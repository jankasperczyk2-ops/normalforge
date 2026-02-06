bl_info = {
    "name": "Auto Custom Normals",
    "author": "Your Name",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Auto Custom Normals",
    "description": "One-click bevel + custom normals workflow for game-ready meshes",
    "category": "Mesh",
}

import bpy
import bmesh
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, IntProperty

ACN_MATERIAL_NAME = "_ACN_BevelTag"
ACN_BACKUP_SUFFIX = "_ACN_Backup"


class ACN_Properties(PropertyGroup):
    bevel_width: FloatProperty(
        name="Bevel Width",
        description="Width of the bevel",
        default=0.02,
        min=0.001,
        max=10.0,
        step=1,
        precision=4,
    )

    bevel_segments: IntProperty(
        name="Segments",
        description="Number of bevel segments",
        default=1,
        min=1,
        max=10,
    )

    auto_sharp_angle: FloatProperty(
        name="Auto Sharp Angle",
        description="Angle threshold for auto-detecting sharp edges",
        default=0.523599,
        min=0.0,
        max=3.14159,
        subtype='ANGLE',
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


def sharp_edges_to_bevel_weight(bm):
    layer = get_bevel_weight_layer(bm)
    count = 0
    for edge in bm.edges:
        if not edge.smooth:
            edge[layer] = 1.0
            count += 1
    return count


def seams_to_bevel_weight(bm):
    layer = get_bevel_weight_layer(bm)
    count = 0
    for edge in bm.edges:
        if edge.seam:
            edge[layer] = 1.0
            count += 1
    return count


def auto_sharp_to_bevel_weight(bm, angle_threshold):
    layer = get_bevel_weight_layer(bm)
    count = 0
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            face_angle = edge.link_faces[0].normal.angle(edge.link_faces[1].normal)
            if face_angle > angle_threshold:
                edge[layer] = 1.0
                edge.smooth = False
                count += 1
        elif len(edge.link_faces) == 1:
            edge[layer] = 1.0
            edge.smooth = False
            count += 1
    return count


def mark_seams_from_bevel_weight(bm):
    layer = get_bevel_weight_layer(bm)
    count = 0
    for edge in bm.edges:
        if edge[layer] > 0.0:
            edge.seam = True
            count += 1
    return count


def get_or_create_tag_material():
    mat = bpy.data.materials.get(ACN_MATERIAL_NAME)
    if mat is None:
        mat = bpy.data.materials.new(name=ACN_MATERIAL_NAME)
        mat.diffuse_color = (1.0, 0.0, 1.0, 0.5)
    return mat


def setup_material_tagging(obj):
    tag_mat = get_or_create_tag_material()

    tag_slot_index = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material and slot.material.name == ACN_MATERIAL_NAME:
            tag_slot_index = i
            break

    if tag_slot_index is None:
        obj.data.materials.append(tag_mat)
        tag_slot_index = len(obj.material_slots) - 1

    return tag_slot_index


def cleanup_tag_material(obj):
    tag_index = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material and slot.material.name == ACN_MATERIAL_NAME:
            tag_index = i
            break

    if tag_index is not None:
        obj.active_material_index = tag_index
        bpy.ops.object.material_slot_remove()

    tag_mat = bpy.data.materials.get(ACN_MATERIAL_NAME)
    if tag_mat and tag_mat.users == 0:
        bpy.data.materials.remove(tag_mat)


def add_bevel_modifier(obj, width, segments, tag_material_index):
    bevel_mod = obj.modifiers.new(name="ACN_Bevel", type='BEVEL')
    bevel_mod.limit_method = 'WEIGHT'
    bevel_mod.width = width
    bevel_mod.segments = segments
    bevel_mod.affect = 'EDGES'
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


def set_normals_from_faces(context):
    ensure_edit_mode(context)
    try:
        bpy.ops.mesh.set_normals_from_faces()
    except Exception:
        pass


def create_mesh_backup(obj):
    backup_name = obj.data.name + ACN_BACKUP_SUFFIX
    existing = bpy.data.meshes.get(backup_name)
    if existing:
        bpy.data.meshes.remove(existing)

    backup_mesh = obj.data.copy()
    backup_mesh.name = backup_name
    return backup_mesh


def restore_mesh_backup(obj):
    backup_name = obj.data.name + ACN_BACKUP_SUFFIX
    if obj.data.name.endswith(ACN_BACKUP_SUFFIX):
        backup_name = obj.data.name

    backup_mesh = bpy.data.meshes.get(backup_name)
    if backup_mesh is None:
        original_name = obj.data.name
        backup_name = original_name + ACN_BACKUP_SUFFIX
        backup_mesh = bpy.data.meshes.get(backup_name)

    if backup_mesh is None:
        return False

    current_mesh = obj.data
    new_mesh = backup_mesh.copy()
    new_mesh.name = current_mesh.name

    obj.data = new_mesh

    bpy.data.meshes.remove(current_mesh)

    leftover = bpy.data.meshes.get(backup_name)
    if leftover:
        bpy.data.meshes.remove(leftover)

    return True


def has_backup(obj):
    backup_name = obj.data.name + ACN_BACKUP_SUFFIX
    return bpy.data.meshes.get(backup_name) is not None


def run_workflow(obj, props):
    tag_index = setup_material_tagging(obj)

    bevel_mod = add_bevel_modifier(obj, props.bevel_width, props.bevel_segments, tag_index)

    bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

    selected = select_original_faces_by_material(obj, tag_index)

    set_normals_from_faces(bpy.context)

    ensure_object_mode(bpy.context)

    cleanup_tag_material(obj)

    return selected


class ACN_OT_from_sharp(Operator):
    """Full workflow starting from sharp edges"""
    bl_idname = "object.acn_from_sharp"
    bl_label = "From Sharp Edges"
    bl_description = "Convert sharp edges to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.acn_props

        ensure_object_mode(context)
        create_mesh_backup(obj)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = sharp_edges_to_bevel_weight(bm)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No sharp edges found on this mesh")
            return {'CANCELLED'}

        mark_seams_from_bevel_weight(bm)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Processed {converted} sharp edges")
        return {'FINISHED'}


class ACN_OT_from_seams(Operator):
    """Full workflow starting from seam edges"""
    bl_idname = "object.acn_from_seams"
    bl_label = "From Seams"
    bl_description = "Convert seam edges to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.acn_props

        ensure_object_mode(context)
        create_mesh_backup(obj)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = seams_to_bevel_weight(bm)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No seam edges found on this mesh")
            return {'CANCELLED'}

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Processed {converted} seam edges")
        return {'FINISHED'}


class ACN_OT_from_bevel_weight(Operator):
    """Full workflow starting from existing bevel weights"""
    bl_idname = "object.acn_from_bevel_weight"
    bl_label = "From Bevel Weights"
    bl_description = "Use existing bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.acn_props

        ensure_object_mode(context)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        layer = bm.edges.layers.float.get("bevel_weight_edge")
        if layer is None:
            bm.free()
            self.report({'WARNING'}, "No bevel weight data found on this mesh")
            return {'CANCELLED'}

        weighted_count = sum(1 for e in bm.edges if e[layer] > 0.0)
        if weighted_count == 0:
            bm.free()
            self.report({'WARNING'}, "No edges with bevel weight found")
            return {'CANCELLED'}

        mark_seams_from_bevel_weight(bm)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        create_mesh_backup(obj)
        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Processed {weighted_count} weighted edges")
        return {'FINISHED'}


class ACN_OT_from_auto_sharp(Operator):
    """Full workflow with auto-detected sharp edges by angle"""
    bl_idname = "object.acn_from_auto_sharp"
    bl_label = "Auto-Detect Sharp"
    bl_description = "Auto-detect sharp edges by angle, convert to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.acn_props

        ensure_object_mode(context)
        create_mesh_backup(obj)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = auto_sharp_to_bevel_weight(bm, props.auto_sharp_angle)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No edges detected above the angle threshold")
            return {'CANCELLED'}

        mark_seams_from_bevel_weight(bm)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        run_workflow(obj, props)

        self.report({'INFO'}, f"Done! Auto-detected {converted} sharp edges")
        return {'FINISHED'}


class ACN_OT_from_existing_bevel(Operator):
    """Apply existing bevel modifier and set custom normals"""
    bl_idname = "object.acn_from_existing_bevel"
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

        tag_index = setup_material_tagging(obj)
        bevel_mod.material = tag_index

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces_by_material(obj, tag_index)

        set_normals_from_faces(bpy.context)

        ensure_object_mode(bpy.context)

        cleanup_tag_material(obj)

        self.report({'INFO'}, "Done! Applied existing bevel and set custom normals")
        return {'FINISHED'}


class ACN_OT_remove(Operator):
    """Remove custom normals and restore original mesh"""
    bl_idname = "object.acn_remove"
    bl_label = "Remove Auto Custom Normals"
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


class ACN_OT_clear_normals(Operator):
    """Clear custom normals without restoring geometry"""
    bl_idname = "object.acn_clear_normals"
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


class ACN_PT_main_panel(Panel):
    bl_label = "Auto Custom Normals"
    bl_idname = "ACN_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Auto Custom Normals'

    def draw(self, context):
        layout = self.layout
        props = context.scene.acn_props
        obj = context.object

        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return

        box = layout.box()
        box.label(text="Bevel Settings", icon='PREFERENCES')
        col = box.column(align=True)
        col.prop(props, "bevel_width")
        col.prop(props, "bevel_segments")

        layout.separator()

        box = layout.box()
        box.label(text="One-Click Workflows", icon='PLAY')

        col = box.column(align=True)
        col.scale_y = 1.3

        col.operator("object.acn_from_sharp", icon='EDGESEL')

        col.separator()
        col.operator("object.acn_from_seams", icon='UV')

        col.separator()
        col.operator("object.acn_from_bevel_weight", icon='MOD_BEVEL')

        col.separator()
        col.operator("object.acn_from_auto_sharp", icon='LIGHT_HEMI')
        col.prop(props, "auto_sharp_angle")

        has_bevel_mod = any(mod.type == 'BEVEL' for mod in obj.modifiers)
        if has_bevel_mod:
            col.separator()
            col.operator("object.acn_from_existing_bevel", icon='CHECKMARK')

        layout.separator()

        box = layout.box()
        box.label(text="Toggle / Restore", icon='FILE_REFRESH')
        col = box.column(align=True)
        col.scale_y = 1.3

        backup_exists = has_backup(obj)
        row = col.row(align=True)
        row.enabled = backup_exists
        row.operator("object.acn_remove", icon='LOOP_BACK', text="Restore Original Mesh")

        col.separator()

        row = col.row(align=True)
        row.enabled = obj.data.has_custom_normals
        row.operator("object.acn_clear_normals", icon='X', text="Clear Custom Normals Only")

        if backup_exists:
            col.label(text="Backup available", icon='CHECKMARK')
        else:
            col.label(text="No backup (run a workflow first)", icon='INFO')

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
    ACN_Properties,
    ACN_OT_from_sharp,
    ACN_OT_from_seams,
    ACN_OT_from_bevel_weight,
    ACN_OT_from_auto_sharp,
    ACN_OT_from_existing_bevel,
    ACN_OT_remove,
    ACN_OT_clear_normals,
    ACN_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.acn_props = bpy.props.PointerProperty(type=ACN_Properties)


def unregister():
    del bpy.types.Scene.acn_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
