bl_info = {
    "name": "Non-Destructive Custom Normals",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Normals",
    "description": "Bake custom normals from evaluated mesh without applying modifiers",
    "category": "Object",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, FloatProperty, EnumProperty


class NDN_Properties(PropertyGroup):
    """Properties for the add-on"""
    auto_update: BoolProperty(
        name="Auto Update",
        description="Automatically update normals when modifiers change",
        default=False
    )
    
    weight_mode: EnumProperty(
        name="Weight Mode",
        description="Method for calculating weighted normals",
        items=[
            ('AREA', 'Face Area', 'Weight by face area'),
            ('ANGLE', 'Corner Angle', 'Weight by corner angle'),
            ('COMBINED', 'Combined', 'Combined area and angle weighting'),
        ],
        default='AREA'
    )
    
    smooth_angle: FloatProperty(
        name="Smooth Angle",
        description="Maximum angle between face normals to smooth",
        default=1.0472,  # 60 degrees in radians
        min=0.0,
        max=3.14159,
        subtype='ANGLE'
    )


class NDN_OT_bake_normals(Operator):
    """Bake custom normals from evaluated mesh (non-destructive)"""
    bl_idname = "object.ndn_bake_normals"
    bl_label = "Bake Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.object
        
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Get the evaluated mesh (after all modifiers)
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()

        if mesh_eval is None:
            self.report({'ERROR'}, "Could not evaluate mesh")
            return {'CANCELLED'}

        # Collect loop normals from the evaluated mesh
        mesh_eval.calc_normals_split()
        loop_normals = [loop.normal.copy() for loop in mesh_eval.loops]

        # Clean up the temporary evaluated mesh
        obj_eval.to_mesh_clear()

        # Apply the normals to the base mesh
        base_mesh = obj.data
        
        # Enable auto smooth (required for custom split normals)
        if hasattr(base_mesh, 'use_auto_smooth'):
            base_mesh.use_auto_smooth = True
        
        # Check if we have matching loop counts
        if len(loop_normals) != len(base_mesh.loops):
            self.report({'WARNING'}, 
                f"Loop count mismatch: evaluated={len(loop_normals)}, base={len(base_mesh.loops)}. "
                "This can happen with topology-changing modifiers.")
            return {'CANCELLED'}

        # Set the custom split normals
        base_mesh.normals_split_custom_set(loop_normals)

        self.report({'INFO'}, f"Baked {len(loop_normals)} custom normals")
        return {'FINISHED'}


class NDN_OT_clear_normals(Operator):
    """Clear custom split normals"""
    bl_idname = "object.ndn_clear_normals"
    bl_label = "Clear Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.object
        
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Clear custom split normals
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        
        self.report({'INFO'}, "Cleared custom normals")
        return {'FINISHED'}


class NDN_OT_weighted_normals(Operator):
    """Calculate weighted normals from evaluated mesh"""
    bl_idname = "object.ndn_weighted_normals"
    bl_label = "Weighted Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.object
        props = context.scene.ndn_props
        
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Get the evaluated mesh
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()

        if mesh_eval is None:
            self.report({'ERROR'}, "Could not evaluate mesh")
            return {'CANCELLED'}

        # Calculate weighted normals based on mode
        mesh_eval.calc_normals_split()
        
        from mathutils import Vector
        import math
        
        # Build vertex -> loop mapping and calculate weighted normals
        vert_normals = {}
        
        for poly in mesh_eval.polygons:
            # Calculate face area for area weighting
            face_area = poly.area
            face_normal = poly.normal
            
            for loop_idx in poly.loop_indices:
                loop = mesh_eval.loops[loop_idx]
                vert_idx = loop.vertex_index
                
                if vert_idx not in vert_normals:
                    vert_normals[vert_idx] = Vector((0, 0, 0))
                
                # Calculate weight based on mode
                if props.weight_mode == 'AREA':
                    weight = face_area
                elif props.weight_mode == 'ANGLE':
                    # Get corner angle
                    prev_idx = poly.loop_indices[(list(poly.loop_indices).index(loop_idx) - 1) % len(poly.loop_indices)]
                    next_idx = poly.loop_indices[(list(poly.loop_indices).index(loop_idx) + 1) % len(poly.loop_indices)]
                    
                    prev_vert = mesh_eval.vertices[mesh_eval.loops[prev_idx].vertex_index].co
                    curr_vert = mesh_eval.vertices[vert_idx].co
                    next_vert = mesh_eval.vertices[mesh_eval.loops[next_idx].vertex_index].co
                    
                    vec1 = (prev_vert - curr_vert).normalized()
                    vec2 = (next_vert - curr_vert).normalized()
                    
                    dot = max(-1, min(1, vec1.dot(vec2)))
                    weight = math.acos(dot)
                else:  # COMBINED
                    weight = face_area
                
                vert_normals[vert_idx] += face_normal * weight
        
        # Normalize the accumulated normals
        for vert_idx in vert_normals:
            if vert_normals[vert_idx].length > 0:
                vert_normals[vert_idx].normalize()
        
        # Build loop normals array
        loop_normals = []
        for loop in mesh_eval.loops:
            if loop.vertex_index in vert_normals:
                loop_normals.append(vert_normals[loop.vertex_index].copy())
            else:
                loop_normals.append(loop.normal.copy())
        
        obj_eval.to_mesh_clear()
        
        # Apply to base mesh
        base_mesh = obj.data
        
        if len(loop_normals) != len(base_mesh.loops):
            self.report({'WARNING'}, "Loop count mismatch with base mesh")
            return {'CANCELLED'}
        
        if hasattr(base_mesh, 'use_auto_smooth'):
            base_mesh.use_auto_smooth = True
        
        base_mesh.normals_split_custom_set(loop_normals)
        
        self.report({'INFO'}, f"Applied weighted normals ({props.weight_mode})")
        return {'FINISHED'}


class NDN_PT_main_panel(Panel):
    """Main panel for Non-Destructive Normals"""
    bl_label = "Non-Destructive Normals"
    bl_idname = "NDN_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Normals'

    def draw(self, context):
        layout = self.layout
        props = context.scene.ndn_props
        obj = context.object

        # Check if we have a valid mesh object
        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return

        # Main operations
        box = layout.box()
        box.label(text="Bake Operations", icon='NORMALS_FACE')
        
        col = box.column(align=True)
        col.operator("object.ndn_bake_normals", icon='CHECKMARK')
        col.operator("object.ndn_weighted_normals", icon='MOD_NORMALEDIT')
        col.operator("object.ndn_clear_normals", icon='X')

        # Weighted normals settings
        box = layout.box()
        box.label(text="Weighted Normals Settings", icon='PREFERENCES')
        box.prop(props, "weight_mode")
        
        # Info section
        box = layout.box()
        box.label(text="Mesh Info", icon='INFO')
        
        mesh = obj.data
        col = box.column(align=True)
        col.label(text=f"Vertices: {len(mesh.vertices)}")
        col.label(text=f"Loops: {len(mesh.loops)}")
        col.label(text=f"Polygons: {len(mesh.polygons)}")
        
        has_custom = mesh.has_custom_normals
        col.label(text=f"Custom Normals: {'Yes' if has_custom else 'No'}")
        
        # Modifier stack info
        if obj.modifiers:
            box = layout.box()
            box.label(text="Active Modifiers", icon='MODIFIER')
            for mod in obj.modifiers:
                row = box.row()
                row.label(text=mod.name, icon='DOT')


# Handler for auto-update (optional feature)
def depsgraph_update_handler(scene, depsgraph):
    """Handler to auto-update normals when modifiers change"""
    if not scene.ndn_props.auto_update:
        return
    
    for update in depsgraph.updates:
        if update.is_updated_geometry:
            obj = update.id
            if hasattr(obj, 'type') and obj.type == 'MESH':
                # Could trigger auto-bake here
                pass


classes = (
    NDN_Properties,
    NDN_OT_bake_normals,
    NDN_OT_clear_normals,
    NDN_OT_weighted_normals,
    NDN_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.ndn_props = bpy.props.PointerProperty(type=NDN_Properties)
    
    # Register handler for auto-update (disabled by default)
    # bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)


def unregister():
    # Unregister handler
    # if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
    #     bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    
    del bpy.types.Scene.ndn_props
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
