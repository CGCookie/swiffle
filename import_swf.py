import bpy
import aud
import os
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from math import isclose, radians
import numpy as np
try:
    import Image
except ImportError:
    from PIL import Image


# Local imports
from . import global_vars
from .lib.globals import *
from .lib.world_env import build_world, rgb_gamma, hex_to_rgba
from .lib.swf.movie import SWF
from .lib.swf.utils import ColorUtils
from .lib.swf.data import SWFCurvedEdge, SWFStraightEdge


def close_points(p1, p2):
    if isclose(p1[0], p2[0], rel_tol=1e-5) and isclose(p1[1], p2[1], rel_tol=1e-5):
        return True
    else:
        return False


def load_swf(filepath):
    f = open(filepath, "rb")
    swf = SWF(f)
    #print(swf)
    f.close()
    return swf


def pil_to_image(pil_image, name = "New Image"):
    """
    Borrowing from StackExchange (https://blender.stackexchange.com/questions/173206/how-to-efficiently-convert-a-pil-image-to-bpy-types-image)
    PIL image pixels is 2D array of byte tuple (when mode is 'RGB', 'RGBA') or byte (when mode is 'L')
    bpy image pixels is flat array of normalized values in RGBA order
    """
    width = pil_image.width
    height = pil_image.height
    byte_to_normalized = 1.0 / 255.0
    bpy_image = bpy.data.images.new(name, width = width, height = height)
    bpy_image.pixels[:] = (np.asarray(pil_image.convert("RGBA"),dtype=np.float32) * byte_to_normalized).ravel()
    return bpy_image

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

    clear_scene: BoolProperty(
        name = "Clear Scene",
        description = "Remove any already existing objects from the scene",
        default = True, # True for debugging; False in production
    )

    swf_data = {}

    def _find_material(self, materials, style_combo):
        #XXX There's a chance that this loop may not find any proper combinations. Hopefully that never happens
        mat_index = 0
        for mat in materials:
            if mat["swf_line_style_idx"] == style_combo["line_style_idx"] and mat["swf_fill_style_idx"] == style_combo["fill_style_idx"]:
                return mat, mat_index
            else:
                mat_index += 1

    def _new_gp_stroke(self, gp_data, gp_frame, copy_mat = False, materials = None, first_edge = None, old_stroke = None):
        gp_stroke = gp_frame.strokes.new()
        if copy_mat == False and first_edge is not None:
            # Figure out which material to use
            style_combo = {
                "line_style_idx": first_edge.line_style_idx,
                "fill_style_idx": first_edge.fill_style_idx
            }
            gp_mat, gp_stroke.material_index = self._find_material(gp_data.materials, style_combo)

            if "swf_linewidth" in gp_mat.keys():
                gp_stroke.line_width = int((gp_mat["swf_linewidth"] / PIXELS_PER_TWIP)) * 10 #XXX Hardcoded multiplier...not sure it's right yet
            else:
                gp_stroke.line_width = 0
        elif old_stroke is not None:
            gp_stroke.material_index = old_stroke.material_index
            gp_stroke.line_width = old_stroke.line_width
        gp_stroke.display_mode = "3DSPACE"
        if copy_mat == False:
            return gp_stroke, gp_mat
        else:
            return gp_stroke

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

    def create_stroke_from_edge_map(self, shapes, edge_map, gp_data, gp_frame, stroke_type):
        # Look for holes, but handle them later
        if stroke_type == "fill" and 0 in edge_map:
            em_holes = {0: edge_map.pop(0)}
        else:
            em_holes = None
        path = shapes._create_path_from_edge_map(edge_map)
        if len(path) > 0:
            first_edge = path[0]
        else:
            return
        gp_stroke, gp_mat = self._new_gp_stroke(gp_data, gp_frame, first_edge = first_edge)
        # Now is where we start working through the edge data
        gp_points = [first_edge.start]
        for edge in path:
            print(edge)
            # Grease pencil doesn't support different materials along a stroke, so we need to start a new stroke if we see one
            if edge.line_style_idx != gp_mat["swf_line_style_idx"] or edge.fill_style_idx != gp_mat["swf_fill_style_idx"]:
                gp_stroke, gp_mat = self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type, new_stroke = True, gp_frame = gp_frame, new_edge = edge)
                gp_points = [edge.start]
            if type(edge) == SWFCurvedEdge:
                # Grease pencil doesn't support "broken" strokes with inline discontinuities. Need to shove a new stroke in when that happens
                if not close_points(edge.start, gp_points[-1]):
                    gp_stroke = self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type, new_stroke = True, gp_frame = gp_frame)
                    gp_points = []
                    _points.append(edge.start)
                knot1 = mathutils.Vector(edge.start)
                knot2 = mathutils.Vector(edge.to)
                control = edge.control
                handle1 = knot1.lerp(mathutils.Vector(control), 2/3) # See SWF spec on converting from quadratic to cubic bezier curves
                handle2 = knot2.lerp(mathutils.Vector(control), 2/3)
                _points = mathutils.geometry.interpolate_bezier(knot1, handle1, handle2, knot2, 12) #XXX Hardcoded resolution value of 12
                # Prevent duplicate points
                if len(gp_points) > 0 and _points[0] == gp_points[-1]:
                    del _points[0]
            elif type(edge) == SWFStraightEdge:
                _points = []
                # Grease pencil doesn't support "broken" strokes with inline discontinuities. Need to shove a new stroke in when that happens
                if not close_points(edge.start, gp_points[-1]):
                    gp_stroke = self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type, new_stroke = True, gp_frame = gp_frame)
                    gp_points = []
                    _points.append(edge.start)
                _points.append(edge.to)
            gp_points.extend(_points)
        self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type)
        # Handle holes (this is recursive, but hopefully it's OK)
        if em_holes is not None:
            #XXX Hack... forcing fill and line style indices to 0
            for edge in em_holes[0]:
                edge.fill_style_idx = 0
                edge.line_style_idx = 0
            self.create_stroke_from_edge_map(shapes, em_holes, gp_data, gp_frame, "hole")

    def _finalize_stroke(self, gp_data, gp_stroke, gp_points, stroke_type, new_stroke = False, gp_frame = None, new_edge = None):
        # Finalize the stroke
        if stroke_type == "line":
            gp_stroke.use_cyclic = False #
        elif stroke_type in ["fill", "hole"]:
            gp_stroke.use_cyclic = True
        for i, point in enumerate(gp_points):
            if close_points(point, gp_points[i - 1]): #XXX Hacky clean-up to remove duplicate points
                continue
            gp_stroke.points.add(1)
            gp_stroke.points[-1].co.x = point[0] / PIXELS_PER_TWIP / PIXELS_PER_METER
            gp_stroke.points[-1].co.y = -point[1] / PIXELS_PER_TWIP / PIXELS_PER_METER

        # Deal with gradient and texture madness
        # Reset fill transforms
        stroke_mat = gp_stroke.id_data.materials[gp_stroke.material_index]
        #if stroke_mat.grease_pencil.fill_style in ["GRADIENT", "TEXTURE"]:
        #    gp_stroke.use_accurate_normal = True #XXX Requires accurate normal patch from Jon Denning
        if stroke_mat.grease_pencil.fill_style == "GRADIENT":
            # So here's something weird... the origin and orientation of a GP stroke is defined by the first and second points on that stroke
            v1 = gp_stroke.points[1].co - gp_stroke.points[0].co
            v2 = mathutils.Vector((0, 1, 0)) # Because we're working in the XY plane
            gp_stroke.uv_rotation = v1.angle(v2) + radians(-90.0)

        # Adjust UV scale if the stroke has a gradient fill
        if "swf_texture_type" in stroke_mat and stroke_mat["swf_texture_type"] == "gradient":
            # Get the stroke's dimensions
            #gp_stroke_dim = gp_stroke.bound_box_max - gp_stroke.bound_box_min
            ref_dim = 32768 / PIXELS_PER_TWIP / PIXELS_PER_METER
            grad_sq_dim = mathutils.Vector((ref_dim, ref_dim))
            grad_dim = mathutils.Vector((2.0, 2.0)) # It appears that strokes have a fixed initial size of 2x2
            # Compare to the intended gradient dimensions
            gp_stroke.uv_scale = grad_sq_dim[0] / grad_dim[0]
        else:
            gp_stroke.uv_scale = 1.0
        # Texture coordinate origin is located -0.5, -0.5 from the location of the first point prior to any rotation, so we need some transform magic
        gp_texture_origin = mathutils.Vector((-0.5, -0.5))
        stroke_center = gp_stroke.bound_box_min.lerp(gp_stroke.bound_box_max, 0.5)
        stroke_origin = gp_stroke.points[0].co.copy()
        # Get the vector from the first point in the stroke to its center
        v_to_center = stroke_center - stroke_origin
        v_to_center.resize_2d()
        m_rotate = mathutils.Matrix.Rotation(-gp_stroke.uv_rotation, 2, "Z")
        # Rotate centering vector to UV space
        v_to_center = gp_texture_origin + (m_rotate @ (v_to_center - gp_texture_origin))
        # Calculate vector from the GP origin to the stroke center
        v_to_center = gp_texture_origin + (v_to_center / 2)
        # Now rotate everything back to geometry space
        #XXX Nothing here seems to work!
        #m_rotate = mathutils.Matrix.Rotation(gp_stroke.uv_rotation, 2, "Z")
        #v_to_center.rotate(m_rotate)
        #v_to_center = gp_texture_origin + (m_rotate @ (v_to_center - gp_texture_origin))
        gp_stroke.uv_translation = v_to_center

        if new_stroke:
            # For SWF lines with discontinuities
            if new_edge is None:
                return self._new_gp_stroke(gp_data, gp_frame, copy_mat = True, old_stroke = gp_stroke)
            else:
                return self._new_gp_stroke(gp_data, gp_frame, first_edge = new_edge)

    def set_material_transforms(self, gp_mat, matrix):
        gp_mat.grease_pencil.mix_factor = 0.0
        gp_matrix = mathutils.Matrix([[matrix.scaleX, matrix.rotateSkew0, 0.0, matrix.translateX / PIXELS_PER_TWIP / PIXELS_PER_METER],
                                      [matrix.rotateSkew1, matrix.scaleY, 0.0, matrix.translateY / PIXELS_PER_TWIP / PIXELS_PER_METER],
                                      [0.0, 0.0, 1.0, 0.0],
                                      [0.0, 0.0, 0.0, 1.0]])
        if gp_mat.grease_pencil.fill_style == "GRADIENT":
            #XXX The following doesn't seem to position the gradient correctly
            # SWF makes the following assumptions:
            #   * Linear gradients default to horizontal (Blender assumes vertical)
            #   * Gradients are defined in a standard space called the "gradient square":
            #     * Origin is 0,0 (image origin)
            #     * Dimensions extend from (-16384,-16384) to (16384,16384) in twips
            ref_dim = 32768 / PIXELS_PER_TWIP / PIXELS_PER_METER # size of the gradient square
            gp_mat["swf_texture_type"] = "gradient"
        elif gp_mat.grease_pencil.fill_style == "TEXTURE":
            ref_dim = gp_mat.grease_pencil.fill_image.size[0] / PIXELS_PER_METER / 10 # size of image

        #print(ref_dim, gp_matrix.decompose()[2][0])
        #gp_mat["swf_texture_intended_width"] = gp_matrix.decompose()[2][0] * ref_dim
        #gp_mat["swf_grad_sq_scaled_height"] = gp_matrix.decompose()[2][1] * ref_sim
        gp_mat.grease_pencil.texture_scale[0] = gp_matrix.decompose()[2][0]
        gp_mat.grease_pencil.texture_scale[1] = gp_matrix.decompose()[2][1]
        gp_mat.grease_pencil.texture_offset[0] = gp_matrix.decompose()[0][0] - 0.5
        gp_mat.grease_pencil.texture_offset[1] = -gp_matrix.decompose()[0][1] - 0.5
        gp_mat.grease_pencil.texture_angle = gp_matrix.decompose()[1].to_euler()[2]

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
            sound_head = None
            mpeg_frames = b""

            if is_sprite:
                # Make container collection for this set of tags
                tag_collection = bpy.data.collections.new("SWF Sprite Tags")
            last_character = None

            #for tag in tags:
            for i, tag in enumerate(tags):
                print(i, tag.name)
                if tag.name == "End":
                    bpy.context.scene.frame_current = orig_frame
                    if len(mpeg_frames) > 0: # There is sound
                        sound_file = open("/tmp/swf_sound.mp3", "wb") #XXX Path should probably be customizable
                        sound_file.write(mpeg_frames)
                        sound_file.close()
                        if not bpy.context.scene.sequence_editor:
                            bpy.context.scene.sequence_editor_create()
                        sound_strip = bpy.context.scene.sequence_editor.sequences.new_sound("swf_sound", "/tmp/swf_sound.mp3", 0, 1)
                    if is_sprite:
                        return tag_collection

                if tag.name.startswith("DefineShape"): # We have a new object to add!
                    #XXX DEBUG
                    #if tag.characterId == 2:
                    #    break
                    # Make a new Grease Pencil object to hold our shapes
                    gp_data = bpy.data.grease_pencils.new(tag.name + ".{0:03}".format(tag.characterId))
                    gp_data["swf_characterId"] = tag.characterId
                    # Build fill and line maps with absolute coordinates and correct style indices
                    tag.shapes._create_edge_maps()
                    line_styles = tag.shapes._lineStyles
                    fill_styles = tag.shapes._fillStyles
                    # Create materials based on initial fill and line styles
                    # This is a bit of a challenge because Grease Pencil materials don't separate fill and line styles for a given shape, so we have to parse the fill edge map and the line edge map to know the combinations ahead of time
                    # Also we have to go through every single edge because SWF supports changing styles midstream on a path. Gross.
                    style_combos = []
                    for edge_map in tag.shapes.line_edge_maps:
                        for edges in edge_map.values():
                            for edge in edges:
                                style_combo = {
                                    "line_style_idx": edge.line_style_idx,
                                    "fill_style_idx": edge.fill_style_idx
                                }
                                if style_combo not in style_combos:
                                    style_combos.append(style_combo)
                    for edge_map in tag.shapes.fill_edge_maps: #XXX Partial copy pasta from above... assumes line edge maps is the same length as fill edge maps
                        for edges in edge_map.values():
                            for edge in edges:
                                style_combo = {
                                    "line_style_idx": edge.line_style_idx,
                                    "fill_style_idx": edge.fill_style_idx
                                }
                                if style_combo not in style_combos:
                                    style_combos.append(style_combo)
                    # Now we create those materials
                    for style_combo in style_combos:
                        # Using a convention here... "SWF Material_LSI-FSI" where LSI is the line style index and FSI is the fill style index
                        mat_name = "SWF Material_{0}-{1}".format(style_combo["line_style_idx"], style_combo["fill_style_idx"])
                        gp_mat = bpy.data.materials.new(mat_name)
                        bpy.data.materials.create_gpencil_data(gp_mat)
                        # Do the line style first
                        if style_combo["line_style_idx"] > 0:
                            line_style = line_styles[style_combo["line_style_idx"] - 1]
                            gp_mat.grease_pencil.color  = hex_to_rgba(hex(ColorUtils.rgb(line_style.color)))
                            gp_mat["swf_linewidth"] = line_style.width
                            gp_mat["swf_line_miter"] = 3.0
                            gp_mat["swf_no_close"] = line_style.no_close
                            gp_mat.grease_pencil.show_stroke = True
                        else:
                            gp_mat.grease_pencil.show_stroke = False
                        gp_mat["swf_line_style_idx"] = style_combo["line_style_idx"]
                        # Now the fill style
                        if style_combo["fill_style_idx"] > 0:
                            fill_style = fill_styles[style_combo["fill_style_idx"] - 1]
                            if fill_style.type == 0: # Solid fill
                                gp_mat.grease_pencil.fill_style = "SOLID"
                                gp_mat.grease_pencil.fill_color = hex_to_rgba(hex(ColorUtils.rgb(fill_style.rgb)))
                            elif fill_style.type in [16, 18, 19]: # Linear or Radial gradient
                                #XXX Only support for two-color gradients in GP fill style gradients; only using first and last gradient record
                                gp_mat.grease_pencil.fill_style = "GRADIENT"
                                if fill_style.type == 16:
                                    gp_mat.grease_pencil.gradient_type = "LINEAR"
                                elif fill_style.type in [18, 19]:
                                    gp_mat.grease_pencil.gradient_type = "RADIAL"
                                gp_mat.grease_pencil.fill_color = hex_to_rgba(hex(ColorUtils.rgb(fill_style.gradient.records[0].color)))
                                gp_mat.grease_pencil.mix_color = hex_to_rgba(hex(ColorUtils.rgb(fill_style.gradient.records[-1].color)))
                                self.set_material_transforms(gp_mat, fill_style.gradient_matrix)
                            elif fill_style.type in [64, 65, 66, 67]: # Bitmap fill
                                gp_mat.grease_pencil.fill_style = "TEXTURE"
                                image = self.swf_data[fill_style.bitmap_id]["data"]
                                gp_mat.grease_pencil.fill_image = image
                                self.set_material_transforms(gp_mat, fill_style.bitmap_matrix)
                            gp_mat.grease_pencil.show_fill = True
                        else:
                            gp_mat.grease_pencil.show_fill = False
                        gp_mat["swf_fill_style_idx"] = style_combo["fill_style_idx"]
                        gp_data.materials.append(gp_mat)

                    # Make a holdout material for holes
                    gp_mat = bpy.data.materials.new("SWF Holdout")
                    bpy.data.materials.create_gpencil_data(gp_mat)
                    gp_mat.grease_pencil.fill_style = "SOLID"
                    gp_mat.grease_pencil.use_fill_holdout = True
                    gp_mat.grease_pencil.show_fill = True
                    gp_mat["swf_line_style_idx"] = 0
                    gp_mat["swf_fill_style_idx"] = 0
                    gp_data.materials.append(gp_mat)

                    # We need some basic layer stuff in our Grease Pencil object for drawing
                    gp_layer = gp_data.layers.new("Layer", set_active = True)
                    gp_frame = gp_layer.frames.new(bpy.context.scene.frame_current) #XXX This is only the first frame... not all of them

                    # Start creating shapes
                    for em_group in range(0, len(tag.shapes.fill_edge_maps)):
                        #XXX Assumes fill_edge_maps and line_edge_maps are of equal length
                        # Start with fills
                        edge_map = tag.shapes.fill_edge_maps[em_group]
                        self.create_stroke_from_edge_map(tag.shapes, edge_map, gp_data, gp_frame, "fill")
                        # Now the lines
                        edge_map = tag.shapes.line_edge_maps[em_group]
                        self.create_stroke_from_edge_map(tag.shapes, edge_map, gp_data, gp_frame, "line")
                    # Populate the swf_data dict with our newly imported stuff
                    self.swf_data[tag.characterId] = {"data": gp_data, "type": "shape"}

                if tag.name == "DefineSprite":
                    sprite_collection = self.parse_tags(tag.tags, is_sprite = True)
                    sprite_instance = bpy.data.objects.new(tag.name, None)
                    sprite_instance["swf_characterId"] = tag.characterId
                    sprite_instance.instance_type = "COLLECTION"
                    sprite_instance.instance_collection = sprite_collection
                    # Populate the swf_data dict with our newly imported stuff
                    self.swf_data[tag.characterId] = {"data": sprite_instance, "type": "sprite"}

                if tag.name == "DefineBitsJPEG2":
                    image = Image.open(tag.bitmapData)
                    img_datablock = pil_to_image(image, name = tag.name)
                    img_datablock["swf_characterId"] = tag.characterId
                    self.swf_data[tag.characterId] = {"data": img_datablock, "type": "image"}

                if tag.name.startswith("PlaceObject"):
                    if tag.hasCharacter and not tag.hasMove:
                        # Add a new character (that we've already defined with ID of characterId)
                        character = self.swf_data[tag.characterId]
                        if character["type"] == "shape":
                            object = bpy.data.objects.new(tag.name + ".{0:03}".format(tag.characterId), character["data"])
                        elif character["type"] == "sprite":
                            object = character["data"]

                        if not is_sprite:
                            bpy.context.collection.objects.link(object)
                        else:
                            tag_collection.objects.link(object)

                        if tag.hasMatrix:
                            self.key_transforms(object, tag.matrix)
                        object["swf_depth"] = tag.depth
                        if hasattr(tag, "instanceName") and tag.instanceName is not None:
                            object.name = tag.instanceName
                        last_character = object

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

                    if tag.hasColorTransform:
                        #XXX Perhaps not the best approach, the HSV modifier doesn't work on GP image textures
                        add_color = rgb_gamma([tag.colorTransform.rAdd, tag.colorTransform.gAdd, tag.colorTransform.bAdd], 2.2)
                        mix_factor = 1.0 - (tag.colorTransform.rMult / 255) #XXX Assumes uniform mixing for R, G, and B
                        last_character.data.layers[0].tint_color = add_color #XXX Assumes only one GP layer
                        last_character.data.layers[0].tint_factor = 1.0
                        for slot in last_character.material_slots:
                            slot.material.grease_pencil.mix_factor = mix_factor

                if tag.name.startswith("TagSoundStreamHead"):
                    sound_head = tag

                if tag.name == "TagSoundStreamBlock":
                    if sound_head.soundFormat == 2: # MP3
                        #XXX Currently only supporting embedded MP3
                        #XXX Also assumes a single embedded sound
                        tag.complete_parse_with_header(sound_head)
                        mpeg_frames += tag.mpegFrames
                
                if tag.name == "ShowFrame":
                    bpy.context.scene.frame_current += 1
                    #break #XXX Only show the first frame for now

    def execute(self, context):
        swf = load_swf(self.filepath)

        if context.active_object is not None and context.active_object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode='OBJECT')

        if self.clear_scene:
            #bpy.ops.wm.read_homefile(app_template="2D_Animation")
            #if context.active_object is not None and context.active_object.mode != "OBJECT":
            #    bpy.ops.object.mode_set(mode='OBJECT')
            for ob in bpy.data.objects:
                bpy.data.objects.remove(ob, do_unlink = True)
            camera_data = bpy.data.cameras.new("SWF Camera")
            camera_ob = bpy.data.objects.new("SWF Camera", camera_data)
            if bpy.data.collections.find("Camera") == -1:
                camera_collection = bpy.data.collections.new("SWF Camera")
                bpy.context.scene.collection.children.link(camera_collection)
            else:
                camera_collection = bpy.data.collections[bpy.data.collections.find("Camera")]
                camera_collection.name = "SWF Camera"
            camera_collection.objects.link(camera_ob)
            bpy.context.scene.camera = camera_ob
            area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
            area.spaces[0].region_3d.view_perspective = 'CAMERA'
        else:
            # Still create the SWF Camera
            camera_data = bpy.data.cameras.new("SWF Camera")
            camera_ob = bpy.data.objects.new("SWF Camera", camera_data)
            camera_collection = bpy.data.collections.new("SWF Camera")
            camera_collection.objects.link(camera_ob)
            bpy.context.scene.collection.children.link(camera_collection)

        # Set up camera, regardless of whether we're adjusting all the world settings
        width = (swf.header.frame_size.xmax - swf.header.frame_size.xmin) / PIXELS_PER_TWIP
        height = (swf.header.frame_size.ymax - swf.header.frame_size.ymin) / PIXELS_PER_TWIP

        #XXX Assume an orthographic camera because taking perspective into account when converting pixels to real units is hard
        camera_ob.data.type = "ORTHO"
        camera_ob.data.ortho_scale = max([width, height]) / PIXELS_PER_METER
        camera_ob.data.shift_x = 0.5
        camera_ob.data.shift_y = -(min([width, height]) * 0.5) / max([width, height])
        camera_ob.location = [0, 0, 10]
        camera_ob.rotation_euler = [0, 0, 0]
        # Store the SWF resolution with the camera data in case we need it later
        camera_ob.data["swf_resolution_x"] = int(width)
        camera_ob.data["swf_resolution_y"] = int(height)

        if self.import_world:
            build_world(swf, width, height)

        self.parse_tags(swf.tags)

        # Hacky clean-up because I think SWF assumes all animations are loops
        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                modifier = fcurve.modifiers.new(type="CYCLES")
                modifier.mode_before = "REPEAT"
                modifier.mode_after = "REPEAT"

        return {"FINISHED"}
