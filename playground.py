import bpy
import os
from math import sin


# Local imports
from . import global_vars
from .lib.globals import *
from .lib.world_env import build_world, hex_to_rgba
from .lib.swf.utils import ColorUtils


class SWF_OT_test_operator(bpy.types.Operator):
    bl_idname = "swf.test_operator"
    bl_label = "Test SWF Import"
    bl_description = "This operator tries to use pyswf to import."
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .lib.swf.movie import SWF
        testfile = open(os.path.abspath(os.path.dirname(__file__) + "/test/star.swf"), "rb")
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
        #        * The shapes themselves seem to live in the records subproperty
        #        * There's a readstyle_array_length subfunction... not sure what it does.
        #    * The PlaceObject and PlaceObject2 tags (types 4 and 26, respectively) tell how and where assets are moved, based on their characterId (defined in the Define[blah] tag)

        orig_frame = bpy.context.scene.frame_current
        bpy.context.scene.frame_current = 1

        for tag in testswf.tags:
            frame_height = bpy.context.scene.render.resolution_y
            if tag.name.startswith("DefineShape"): # We have a new object to add!
                # Make a new Grease Pencil object to hold our shapes
                gp_data = bpy.data.grease_pencils.new(tag.name + ".{0:03}".format(tag.characterId))
                gp_object = bpy.data.objects.new(tag.name + ".{0:03}".format(tag.characterId), gp_data)
                gp_object["swf_characterId"] = tag.characterId
                # Define initial fill and line materials
                for fill_style in tag.shapes._initialFillStyles:
                    gp_mat = bpy.data.materials.new("FillStyle")
                    bpy.data.materials.create_gpencil_data(gp_mat)
                    gp_mat.grease_pencil.show_stroke = False
                    gp_mat.grease_pencil.show_fill = True
                    gp_mat.grease_pencil.fill_color = hex_to_rgba(ColorUtils.to_rgb_string(fill_style.rgb))
                    if fill_style.type == 0:
                        gp_mat.grease_pencil.fill_style = "SOLID"
                    else:
                        raise Exception("Non-solid fill types are currently not supported")
                    gp_data.materials.append(gp_mat)
                for line_style in tag.shapes._initialLineStyles:
                    gp_mat = bpy.data.materials.new("LineStyle")
                    bpy.data.materials.create_gpencil_data(gp_mat)
                    gp_mat.grease_pencil.show_stroke = True
                    if line_style.fill_type == None:
                        gp_mat.grease_pencil.show_fill = False
                    else:
                        raise Exception("Filled line styles not currently supported")
                    gp_mat.grease_pencil.color  = hex_to_rgba(ColorUtils.to_rgb_string(line_style.color))
                    gp_mat["swf_linewidth"] = line_style.width
                    gp_mat["swf_line_miter"] = 3.0
                    gp_data.materials.append(gp_mat)

                # We need some basic layer stuff in our Grease Pencil object for drawing
                gp_layer = gp_data.layers.new("Layer", set_active = True)
                gp_frame = gp_layer.frames.new(bpy.context.scene.frame_current) #XXX This is only the first frame... not all of them
                # Start creating shapes
                draw_pos = [0.0, 0.0] #XXX Should start as the object/shape origin
                for shape in tag.shapes.records:
                    if shape.type == 1: # EndShapeRecord... this should be the last shape record
                        break
                    elif shape.type == 2: # StyleChangeRecord
                        if shape.state_moveto:
                            move_x = shape.move_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER
                            move_y = shape.move_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER
                            draw_pos = [move_x, -move_y]
                            print("Draw Position:", draw_pos)
                            bpy.context.scene.cursor.location = [draw_pos[0], draw_pos[1], 0]
                        #XXX Still need to handle fill and line style selection
                    elif shape.type == 3: # StraightEdgeRecord
                        gp_stroke = gp_frame.strokes.new()
                        gp_stroke.line_width = 20 #XXX placeholder
                        gp_stroke.display_mode = "3DSPACE"
                        gp_stroke.material_index = 0 #XXX placeholder
                        start = draw_pos
                        end = [draw_pos[0] + (shape.deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                               draw_pos[1] - (shape.deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        gp_points = [start, end]
                        draw_pos = end
                        print(gp_points)
                        for point in gp_points:
                            gp_stroke.points.add(1)
                            gp_stroke.points[-1].co.x = point[0]
                            gp_stroke.points[-1].co.y = point[1]
                    elif shape.type == 4: # CurvedEdgeRecord
                        gp_stroke = gp_frame.strokes.new()
                        gp_stroke.line_width = 20 #XXX placeholder
                        gp_stroke.display_mode = "3DSPACE"
                        gp_stroke.material_index = 0 #XXX placeholder
                        anchor1 = draw_pos
                        control = [draw_pos[0] + (shape.control_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   draw_pos[1] - (shape.control_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        anchor2 = [control[0] + (shape.anchor_deltaX / PIXELS_PER_TWIP / PIXELS_PER_METER),
                                   control[1] - (shape.anchor_deltaY / PIXELS_PER_TWIP / PIXELS_PER_METER)]
                        gp_points = [anchor1, control, anchor1]
                        draw_pos = anchor2
                        print(gp_points)
                        for point in gp_points:
                            gp_stroke.points.add(1)
                            gp_stroke.points[-1].co.x = point[0]
                            gp_stroke.points[-1].co.y = point[1]

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

        '''
        # Here's a dumb idea... use pyswf's built-in convert to SVG function... then import that using Blender's SVG importer
        from .lib.swf.export import SVGExporter
        svg_exporter = SVGExporter()
        testsvg = testswf.export(svg_exporter)
        # Temp output
        tmpout_path = "/tmp/swfimport.svg"

        open(tmpout_path, "wb").write(testsvg.read())
        #bpy.ops.wm.gpencil_import_svg(filepath=tmpout_path, scale=100, resolution=100) #XXX This seems so not be functional
        bpy.ops.import_curve.svg(filepath=tmpout_path) # Then convert to Grease Pencil. Not ideal, but it kind of works
        '''

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
