import bpy
import os
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from math import isclose


# Local imports
from . import global_vars
from .lib.globals import *
from .lib.world_env import build_world, hex_to_rgba
from .lib.swf.movie import SWF
from .lib.swf.utils import ColorUtils


def close_points(p1, p2):
    if isclose(p1[0], p2[0], rel_tol=1e-5) and isclose(p1[1], p2[1], rel_tol=1e-5):
        return True
    else:
        return False


def load_swf(context, filepath):
    f = open(filepath, "rb")
    swf = SWF(f)
    #print(swf)
    f.close()
    return swf


class SWF_OT_import(bpy.types.Operator, ImportHelper):
    """Import SWF file as Grease Pencil animation"""
    bl_idname = "swf.import_swf"
    bl_label = "SWF Import"
    bl_description = "Import SWF file as Grease Pencil animation."
    bl_options = {"REGISTER"}

    filename_ext = ".swf"

    filter_glob: StringProperty(
        default = "*.swf",
        options = {"HIDDEN"},
        maxlen = 255,
    )

    import_world: BoolProperty(
        name = "Import World",
        description = "Include world, camera, and framerate settings from SWF",
        default = True,
    )

    def key_transforms(self, object, matrix):
        #XXX Blender doesn't support shearing at the object level, so the rotateSkew0 and rotateSkew1 values can only be used for rotation
        m = mathutils.Matrix([[matrix.scaleX, matrix.rotateSkew0, 0.0, matrix.translateX / PIXELS_PER_TWIP / PIXELS_PER_METER],
                              [matrix.rotateSkew1, matrix.scaleY, 0.0, -matrix.translateY / PIXELS_PER_TWIP / PIXELS_PER_METER],
                              [0.0, 0.0, 1.0, 0.0],
                              [0.0, 0.0, 0.0, 1.0]])
        object.matrix_world = m
        object.keyframe_insert("location")
        object.keyframe_insert("rotation_euler")
        object.keyframe_insert("scale")

    def parse_tags(self, tags, is_sprite = False):
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
            #    * If you run into a DefineSprite tag, the whole process above gets nested. Current plan is to make a collection and place it as a collection instance

            orig_frame = bpy.context.scene.frame_current
            bpy.context.scene.frame_current = 1

            # Make container collection for this set of tags
            tag_collection = bpy.data.collections.new("SWF Tags")
            last_character = None

            for tag in tags:
                if tag.name == "End":
                    bpy.context.scene.frame_current = orig_frame
                    return tag_collection

                if tag.name.startswith("DefineShape"): # We have a new object to add!
                    # Make a new Grease Pencil object to hold our shapes
                    gp_data = bpy.data.grease_pencils.new(tag.name + ".{0:03}".format(tag.characterId))
                    gp_object = bpy.data.objects.new(tag.name + ".{0:03}".format(tag.characterId), gp_data)
                    tag_collection.objects.link(gp_object)
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

                if tag.name == "DefineSprite":
                    sprite_collection = self.parse_tags(tag.tags, is_sprite = True)
                    sprite_instance = bpy.data.objects.new(tag.name, None)
                    sprite_instance["swf_characterId"] = tag.characterId
                    sprite_instance.instance_type = "COLLECTION"
                    sprite_instance.instance_collection = sprite_collection

                if tag.name.startswith("PlaceObject"):
                    if tag.hasCharacter and not tag.hasMove:
                        # Add a new character (that we've already defined with ID of characterId)
                        # Find the object we already created with the identified character ID
                        ob_is_found = False
                        for ob in bpy.data.objects:
                            if "swf_characterId" in ob.keys() and ob["swf_characterId"] == tag.characterId:
                                if not is_sprite:
                                    bpy.context.collection.objects.link(ob)
                                else:
                                    tag_collection.objects.link(ob)
                                if tag.hasMatrix:
                                    self.key_transforms(ob, tag.matrix)
                                ob["swf_depth"] = tag.depth
                                if hasattr(tag, "instanceName") and tag.instanceName is not None:
                                    ob.name = tag.instanceName
                                last_character = ob
                                ob_is_found = True
                                break
                        if not ob_is_found:
                            raise Exception("Trying to place an object/characterId that hasn't been defined.")

                    elif not tag.hasCharacter and tag.hasMove:
                        # Character at given depth (only one character is allowed at a given depth) has been modified
                        #XXX This only works if last_character has been previously set
                        if last_character is not None:
                            if tag.hasMatrix:
                                self.key_transforms(last_character, tag.matrix)
                        else:
                            raise Exception("Trying to modify an object/character that has not yet been placed")

                    #if tag.hasCharacter and tag.hasMove:
                        # Character at given depth is removed. New character (already defined with ID of characterId) is added at given depth
                        #break

                if tag.name == "ShowFrame":
                    bpy.context.scene.frame_current += 1

    def execute(self, context):
        swf = load_swf(context, self.filepath)

        if self.import_world:
            build_world(swf)

        self.parse_tags(swf.tags)

        # Hacky clean-up because I think SWF assumes all animations are loops
        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                modifier = fcurve.modifiers.new(type="CYCLES")
                modifier.mode_before = "REPEAT"
                modifier.mode_after = "REPEAT"

        return {"FINISHED"}
