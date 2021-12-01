import bpy
import os
import mathutils
from math import sin, isclose


# Local imports
from . import global_vars
from .lib.globals import *
from .lib.world_env import build_world, hex_to_rgba
from .lib.swf.utils import ColorUtils

def close_points(p1, p2):
    if isclose(p1[0], p2[0], rel_tol=1e-5) and isclose(p1[1], p2[1], rel_tol=1e-5):
        return True
    else:
        return False

class SWF_OT_test_operator(bpy.types.Operator):
    bl_idname = "swf.test_operator"
    bl_label = "Test SWF Import"
    bl_description = "This operator tries to use pyswf to import."
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .lib.swf.movie import SWF
        testfile = open(os.path.abspath(os.path.dirname(__file__) + "/test/bumble-bee1.swf"), "rb")
        testswf = SWF(testfile)
        #print(testswf)

        build_world(testswf)

        # Parsing should basically look like this:
        #  * Iterate through all tags in order.
        #    * For every ShowFrame tag (type TagShowFrame, or 1), increment the current frame after processing.
        #    * All tags preceding the ShowFrame tag are potential candidates for being displayed on that previous frame.
        #    * Look for Define[Shape4,Sprite,etc] tags to dictate the actual objects added to the scene
        #      * DefineShape is another loop
        #        * In the the DefineShape4 is a property called shapes that has all the shapes
        #        * There are subproperties, _initialFillStyles and _initialLineStyles that have stoke and fill definitions
        #        * The shapes themselves seem to live in the records subproperty... treat them as a stream
        #          * Loop through shape records. Each StyleChangeRecord constitutes a new, disconnected GP stroke
        #    * The PlaceObject and PlaceObject2 tags (types 4 and 26, respectively) tell how and where assets are moved, based on their characterId (defined in the Define[blah] tag)

        orig_frame = bpy.context.scene.frame_current
        bpy.context.scene.frame_current = 1

        for tag in testswf.tags:
            if tag.name.startswith("DefineShape"): # We have a new object to add!
                # Make a new Grease Pencil object to hold our shapes
                gp_data = bpy.data.grease_pencils.new(tag.name + ".{0:03}".format(tag.characterId))
                gp_object = bpy.data.objects.new(tag.name + ".{0:03}".format(tag.characterId), gp_data)
                gp_object["swf_characterId"] = tag.characterId
                fill_styles = tag.shapes._initialFillStyles
                line_styles = tag.shapes._initialLineStyles

                # We need some basic layer stuff in our Grease Pencil object for drawing
                gp_layer = gp_data.layers.new("Layer", set_active = True)
                gp_frame = gp_layer.frames.new(bpy.context.scene.frame_current) #XXX This is only the first frame... not all of them
                # Start creating shapes
                draw_pos = [0.0, 0.0] #XXX Should start as the object/shape origin
                gp_points = []
                #shapecount = 0
                for shape in tag.shapes.records:
                    if shape.type == 1: # EndShapeRecord... this should be the last shape record
                        # Add the points for the last shape
                        if close_points(gp_points[0], gp_points[-1]):
                            gp_stroke.use_cyclic = True #XXX Ignoring the no_close line style attribute for the time being
                            gp_points.pop()
                        else:
                            gp_stroke.use_cyclic = False
                        for i, point in enumerate(gp_points):
                            if close_points(point, gp_points[i - 1]): #XXX Hacky clean-up to remove duplicate points
                                continue
                            gp_stroke.points.add(1)
                            gp_stroke.points[-1].co.x = point[0]
                            gp_stroke.points[-1].co.y = point[1]
                        break
                    elif shape.type == 2: # StyleChangeRecord
                        # If this isn't the first StyleChangeRecord, draw the points in the preceding stroke
                        if len(gp_points) > 1:
                            #print("Shape Count:", shapecount)
                            if close_points(gp_points[0], gp_points[-1]):
                                gp_stroke.use_cyclic = True #XXX Ignoring the no_close line style attribute for the time being
                                gp_points.pop()
                            else:
                                gp_stroke.use_cyclic = False
                            for i, point in enumerate(gp_points):
                                if close_points(point, gp_points[i - 1]): #XXX Hacky clean-up to remove duplicate points
                                    continue
                                gp_stroke.points.add(1)
                                gp_stroke.points[-1].co.x = point[0]
                                gp_stroke.points[-1].co.y = point[1]
                            #if shapecount == 7:
                            #    break
                            #shapecount += 1
                        # Check for new fill styles and line styles
                        if shape.state_new_styles:
                            if len(shape.fill_styles) > 0:
                                fill_styles = shape.fill_styles
                            if len(shape.line_styles) > 0:
                                line_styles = shape.line_styles
                        # Create material based on fill style and line style
                        #XXX In an ideal world, we'll check to see if this material combination already exists
                        if shape.state_fill_style0 or shape.state_fill_style1 or shape.state_line_style:
                            gp_mat = bpy.data.materials.new("SWF Material")
                            bpy.data.materials.create_gpencil_data(gp_mat)
                            if shape.state_fill_style0 or shape.state_fill_style1: #XXX For now assume XOR
                                if shape.state_fill_style0:
                                    fill_style = fill_styles[shape.fill_style0 - 1]
                                elif shape.state_fill_style1:
                                    fill_style = fill_styles[shape.fill_style1 - 1]
                                    if len(gp_data.materials) > 0: #XXX Hack that prevents the first stroke from using a holdout material
                                        gp_mat.grease_pencil.use_fill_holdout = True #XXX Seems to work most of the time...
                                gp_mat.grease_pencil.fill_color = hex_to_rgba(hex(ColorUtils.rgb(fill_style.rgb)))
                                if fill_style.type == 0:
                                    gp_mat.grease_pencil.fill_style = "SOLID" #XXX Still need to support other fill types
                                gp_mat.grease_pencil.show_fill = True
                            else:
                                gp_mat.grease_pencil.show_fill = False
                            if shape.state_line_style:
                                line_style = line_styles[shape.line_style - 1]
                                gp_mat.grease_pencil.color  = hex_to_rgba(hex(ColorUtils.rgb(line_style.color)))
                                gp_mat["swf_linewidth"] = line_style.width
                                gp_mat["swf_line_miter"] = 3.0
                                gp_mat["swf_no_close"] = line_style.no_close
                                gp_mat.grease_pencil.show_stroke = True
                            else:
                                gp_mat.grease_pencil.show_stroke = False
                        gp_data.materials.append(gp_mat)
                        # Start creating a stroke, but don't commit it yet
                        gp_stroke = gp_frame.strokes.new()
                        if "swf_linewidth" in gp_mat.keys():
                            gp_stroke.line_width = (gp_mat["swf_linewidth"] / PIXELS_PER_TWIP) * 10 #XXX Hardcoded multiplier...not sure it's right yet
                        else:
                            gp_stroke.line_width = 0
                        gp_stroke.display_mode = "3DSPACE"
                        gp_stroke.material_index = len(gp_data.materials) - 1 #XXX This would need to be smarter if we're checking for already created materials
                        gp_points = []
                        if shape.state_moveto:
                            move_x = shape.move_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER
                            move_y = shape.move_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER
                            draw_pos = [move_x, -move_y]
                        gp_points.append(draw_pos)
                    elif shape.type == 3: # StraightEdgeRecord
                        if shape.general_line_flag:
                            end = [draw_pos[0] + (shape.deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   draw_pos[1] - (shape.deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        elif shape.vert_line_flag:
                            end = [draw_pos[0],
                                   draw_pos[1] - (shape.deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        else:
                            end = [draw_pos[0] + (shape.deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   draw_pos[1]]
                        gp_points.append(end)
                        draw_pos = end
                    elif shape.type == 4: # CurvedEdgeRecord
                        anchor1 = draw_pos
                        control = [draw_pos[0] + (shape.control_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   draw_pos[1] - (shape.control_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        anchor2 = [control[0] + (shape.anchor_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   control[1] - (shape.anchor_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        knot1 = mathutils.Vector(anchor1)
                        knot2 = mathutils.Vector(anchor2)
                        handle1 = knot1.lerp(mathutils.Vector(control), 2/3) # See SWF spec on converting from quadratic to cubic bezier curves
                        handle2 = knot2.lerp(mathutils.Vector(control), 2/3)
                        _points = mathutils.geometry.interpolate_bezier(knot1, handle1, handle2, knot2, 6) #XXX Hardcoded resolution value of 6
                        gp_points.extend(_points)
                        draw_pos = anchor2

            if tag.name.startswith("PlaceObject"):
                if tag.hasCharacter and not tag.hasMove:
                    # Add a new character (that we've already defined with ID of characterId)
                    # Find the object we already created with the identified character ID
                    ob_is_found = False
                    for ob in bpy.data.objects:
                        if "swf_characterId" in ob.keys() and ob["swf_characterId"] == tag.characterId:
                            bpy.context.collection.objects.link(ob)
                            if tag.hasMatrix:
                                #XXX Blender doesn't support shearing at the object level, so the rotateSkew0 and rotateSkew1 values can only be used for rotation
                                translate_x = tag.matrix.translateX / PIXELS_PER_TWIP / PIXELS_PER_METER
                                translate_y = -tag.matrix.translateY / PIXELS_PER_TWIP / PIXELS_PER_METER
                                rotation_z = sin(tag.matrix.rotateSkew0)
                                ob.location = (ob.location[0] + translate_x, ob.location[1] + translate_y, ob.location[2])
                                ob.rotation_euler[1] += rotation_z
                                ob.scale = (tag.matrix.scaleX, tag.matrix.scaleY, ob.scale[2])

                            ob["swf_depth"] = tag.depth
                            ob_is_found = True
                            break
                    if not ob_is_found:
                        raise Exception("Trying to place an object/characterId that hasn't been defined.")
                #if not tag.hasCharacter and tag.hasMove:
                    # Character at given depth (only one character is allowed at a given depth) has been modified
                    #break
                #if tag.hasCharacter and tag.hasMove:
                    # Character at given depth is removed. New character (already defined with ID of characterId) is added at given depth
                    #break

            if tag.name == "ShowFrame":
                bpy.context.scene.frame_current += 1

        bpy.context.scene.frame_end = bpy.context.scene.frame_current - 1
        bpy.context.scene.frame_current = orig_frame

        return {"FINISHED"}


class SWF_PT_panel(bpy.types.Panel):
    bl_label = "SWF Import Panel"
    bl_category = "SWF Import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        layout.operator(SWF_OT_test_operator.bl_idname)


class SWF_PT_warning_panel(bpy.types.Panel):
    bl_label = "Warning"
    bl_category = "SWF Import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    @classmethod
    def poll(self, context):
        return not global_vars.dependencies_installed

    def draw(self, context):
        layout = self.layout

        lines = [f"Please install the missing dependencies for the add-on.",
                 f"1. Open the preferences (Edit > Preferences > Add-ons).",
                 f"2. Search for the add-on.",
                 f"3. Open the details section of the add-on.",
                 f"4. Click on the Install Dependencies button.",
                 f"   This will download and install the missing Python packages, if Blender has the required",
                 f"   permissions.",
                 f"If you're attempting to run the add-on from the text editor, you won't see the options described",
                 f"above. Please install the add-on properly through the preferences.",
                 f"1. Open the add-on preferences (Edit > Preferences > Add-ons).",
                 f"2. Press the \"Install\" button.",
                 f"3. Search for the add-on file.",
                 f"4. Confirm the selection by pressing the \"Install Add-on\" button in the file browser."]

        for line in lines:
            layout.label(text=line)
