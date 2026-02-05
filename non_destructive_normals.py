bl_info = {
    "name": "Non-Destructive Custom Normals",
    "author": "Your Name",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Normals",
    "description": "One-click bevel + custom normals workflow for game-ready meshes",
    "category": "Object",
}

import bpy
import bmesh
import math
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, EnumProperty, IntProperty


class NDN_Properties(PropertyGroup):
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


def deselect_all_edges(bm):
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False
    for v in bm.verts:
        v.select = False


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


def add_bevel_modifier(obj, width, segments):
    bevel_mod = obj.modifiers.new(name="NDN_Bevel", type='BEVEL')
    bevel_mod.limit_method = 'WEIGHT'
    bevel_mod.width = width
    bevel_mod.segments = segments
    bevel_mod.affect = 'EDGES'
    bevel_mod.harden_normals = False
    return bevel_mod


def get_bevel_face_indices(obj, bm_before):
    before_face_count = len(bm_before.faces)
    return before_face_count


def select_original_faces(obj, original_face_count):
    ensure_edit_mode(bpy.context)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    deselect_all_edges(bm)
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    selected = 0
    for i, face in enumerate(bm.faces):
        if i < original_face_count:
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


class NDN_OT_from_sharp(Operator):
    """Full workflow starting from sharp edges"""
    bl_idname = "object.ndn_from_sharp"
    bl_label = "From Sharp Edges"
    bl_description = "Convert sharp edges to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.ndn_props

        ensure_object_mode(context)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = sharp_edges_to_bevel_weight(bm)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No sharp edges found on this mesh")
            return {'CANCELLED'}

        seams_marked = mark_seams_from_bevel_weight(bm)

        original_face_count = len(bm.faces)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        bevel_mod = add_bevel_modifier(obj, props.bevel_width, props.bevel_segments)

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces(obj, original_face_count)

        set_normals_from_faces(context)

        ensure_object_mode(context)

        self.report({'INFO'}, f"Done! Processed {converted} sharp edges, marked {seams_marked} seams")
        return {'FINISHED'}


class NDN_OT_from_seams(Operator):
    """Full workflow starting from seam edges"""
    bl_idname = "object.ndn_from_seams"
    bl_label = "From Seams"
    bl_description = "Convert seam edges to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.ndn_props

        ensure_object_mode(context)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = seams_to_bevel_weight(bm)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No seam edges found on this mesh")
            return {'CANCELLED'}

        original_face_count = len(bm.faces)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        bevel_mod = add_bevel_modifier(obj, props.bevel_width, props.bevel_segments)

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces(obj, original_face_count)

        set_normals_from_faces(context)

        ensure_object_mode(context)

        self.report({'INFO'}, f"Done! Processed {converted} seam edges")
        return {'FINISHED'}


class NDN_OT_from_bevel_weight(Operator):
    """Full workflow starting from existing bevel weights"""
    bl_idname = "object.ndn_from_bevel_weight"
    bl_label = "From Bevel Weights"
    bl_description = "Use existing bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.ndn_props

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

        seams_marked = mark_seams_from_bevel_weight(bm)
        original_face_count = len(bm.faces)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        bevel_mod = add_bevel_modifier(obj, props.bevel_width, props.bevel_segments)

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces(obj, original_face_count)

        set_normals_from_faces(context)

        ensure_object_mode(context)

        self.report({'INFO'}, f"Done! Processed {weighted_count} weighted edges, marked {seams_marked} seams")
        return {'FINISHED'}


class NDN_OT_from_auto_sharp(Operator):
    """Full workflow with auto-detected sharp edges by angle"""
    bl_idname = "object.ndn_from_auto_sharp"
    bl_label = "Auto-Detect Sharp"
    bl_description = "Auto-detect sharp edges by angle, convert to bevel weights, add bevel, apply, and set custom normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        props = context.scene.ndn_props

        ensure_object_mode(context)

        bm = bmesh.new()
        bm.from_mesh(obj.data)

        converted = auto_sharp_to_bevel_weight(bm, props.auto_sharp_angle)
        if converted == 0:
            bm.free()
            self.report({'WARNING'}, "No edges detected above the angle threshold")
            return {'CANCELLED'}

        seams_marked = mark_seams_from_bevel_weight(bm)
        original_face_count = len(bm.faces)

        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        bevel_mod = add_bevel_modifier(obj, props.bevel_width, props.bevel_segments)

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces(obj, original_face_count)

        set_normals_from_faces(context)

        ensure_object_mode(context)

        self.report({'INFO'}, f"Done! Auto-detected {converted} sharp edges, marked {seams_marked} seams")
        return {'FINISHED'}


class NDN_OT_from_existing_bevel(Operator):
    """Apply existing bevel modifier and set custom normals"""
    bl_idname = "object.ndn_from_existing_bevel"
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

        bevel_mod = None
        for mod in obj.modifiers:
            if mod.type == 'BEVEL':
                bevel_mod = mod
                break

        if bevel_mod is None:
            self.report({'WARNING'}, "No bevel modifier found")
            return {'CANCELLED'}

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        original_face_count = len(bm.faces)

        layer = get_bevel_weight_layer(bm)
        mark_seams_from_bevel_weight(bm)
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

        bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

        select_original_faces(obj, original_face_count)

        set_normals_from_faces(context)

        ensure_object_mode(context)

        self.report({'INFO'}, f"Done! Applied existing bevel modifier and set custom normals")
        return {'FINISHED'}


class NDN_PT_main_panel(Panel):
    bl_label = "Non-Destructive Normals"
    bl_idname = "NDN_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Normals'

    def draw(self, context):
        layout = self.layout
        props = context.scene.ndn_props
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

        col.operator("object.ndn_from_sharp", icon='EDGESEL')

        col.separator()
        col.operator("object.ndn_from_seams", icon='UV')

        col.separator()
        col.operator("object.ndn_from_bevel_weight", icon='MOD_BEVEL')

        col.separator()
        row = col.row(align=True)
        row.operator("object.ndn_from_auto_sharp", icon='LIGHT_HEMI')
        col.prop(props, "auto_sharp_angle")

        has_bevel_mod = any(mod.type == 'BEVEL' for mod in obj.modifiers)
        if has_bevel_mod:
            col.separator()
            col.operator("object.ndn_from_existing_bevel", icon='CHECKMARK')

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
    NDN_Properties,
    NDN_OT_from_sharp,
    NDN_OT_from_seams,
    NDN_OT_from_bevel_weight,
    NDN_OT_from_auto_sharp,
    NDN_OT_from_existing_bevel,
    NDN_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ndn_props = bpy.props.PointerProperty(type=NDN_Properties)


def unregister():
    del bpy.types.Scene.ndn_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
