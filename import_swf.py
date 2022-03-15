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
    if isclose(p1[0], p2[0], rel_tol=1e-5, abs_tol=0.001) and isclose(p1[1], p2[1], rel_tol=1e-5, abs_tol=0.001):
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


def swf_matrix_to_blender_matrix(matrix):
    m = mathutils.Matrix([[matrix.scaleX, matrix.rotateSkew0, 0.0, matrix.translateX / PIXELS_PER_TWIP / PIXELS_PER_METER],
                          [matrix.rotateSkew1, matrix.scaleY, 0.0, -matrix.translateY / PIXELS_PER_TWIP / PIXELS_PER_METER],
                          [0.0, 0.0, 1.0, 0.0],
                          [0.0, 0.0, 0.0, 1.0]])
    return m


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
    swf_style_map = []
    swf_layer_matrices = {}
    swf_collection = None

    def _find_material(self, style_combo):
        for mapping in self.swf_style_map:
            if mapping["line_style"] == style_combo["line_style"] and mapping["fill_style"] == style_combo["fill_style"]:
                return mapping["material"]
        print("No matching material")
        return None

    def _setup_material(self, ob_data, shapes, edge_map, edge):
        style_combo = {
            "line_style": shapes._lineStyles[edge.line_style_idx - 1] if edge.line_style_idx > 0 else None,
            "fill_style": shapes._fillStyles[edge.fill_style_idx - 1] if edge.fill_style_idx > 0 else None
        }
        mat = self._find_material(style_combo)
        if mat is not None and mat.name not in ob_data.materials:
            ob_data.materials.append(mat)
        return mat

    def _new_gp_stroke(self, gp_data, gp_frame, gp_mat, copy_mat = False):
        gp_stroke = gp_frame.strokes.new()
        gp_stroke.material_index = {gp_mat.name: i for i, gp_mat in enumerate(gp_data.materials)}[gp_mat.name]
        if copy_mat == False:
            if "swf_linewidth" in gp_mat.keys():
                gp_stroke.line_width = int((gp_mat["swf_linewidth"] / PIXELS_PER_TWIP)) * 10 #XXX Hardcoded multiplier...not sure it's right yet
            else:
                gp_stroke.line_width = 0
        else:
            if "swf_linewidth" in gp_mat.keys():
                gp_stroke.line_width = gp_mat["swf_linewidth"]
            else:
                gp_stroke.line_width = 0
        gp_stroke.display_mode = "3DSPACE"
        return gp_stroke

    def _transform_strokes(self, strokes, matrix, object_matrix):
        if type(matrix) == mathutils.Matrix:
            m = matrix
        else:
            m = swf_matrix_to_blender_matrix(matrix)
        transform_matrix = object_matrix.inverted() @ m
        for stroke in strokes:
            for point in stroke.points:
                point.co = transform_matrix @ point.co

    def _key_transforms(self, object, matrix, depth = 0):
        #XXX Blender doesn't support shearing at the object level, so the rotateSkew0 and rotateSkew1 values can only be used for rotation
        m = swf_matrix_to_blender_matrix(matrix)
        object.matrix_world = m
        object.location[2] = depth / 100 # Hacky attempt to get at least some kind of z-order at the object level
        object.keyframe_insert(data_path = "location")
        object.keyframe_insert(data_path = "rotation_euler")
        object.keyframe_insert(data_path = "scale")

    def create_stroke_from_edge_map(self, shapes, edge_map, gp_data, gp_frame, stroke_type):
        # Look for holes, but handle them later
        if stroke_type == "fill" and 0 in edge_map:
            em_holes = {0: edge_map.pop(0)}
        else:
            em_holes = None
        path = shapes._create_path_from_edge_map(edge_map)
        if len(path) > 0:
            ref_edge = path[0]
            gp_mat = self._setup_material(gp_data, shapes, edge_map, ref_edge)
        else:
            return
        gp_stroke = self._new_gp_stroke(gp_data, gp_frame, gp_mat)

        # Now is where we start working through the edge data
        gp_points = [ref_edge.start]
        for edge in path:
            #print(edge)
            # Grease pencil doesn't support different materials along a stroke, so we need to start a new stroke if we see one
            if edge.line_style_idx != ref_edge.line_style_idx or edge.fill_style_idx != ref_edge.fill_style_idx:
                gp_mat = self._setup_material(gp_data, shapes, edge_map, edge)
                gp_stroke = self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type, new_stroke = True, gp_frame = gp_frame, new_mat = gp_mat)
                gp_points = [edge.start]
                ref_edge = edge

            _points = []
            # Grease pencil doesn't support "broken" strokes with inline discontinuities. Need to shove a new stroke in when that happens
            if not close_points(edge.start, gp_points[-1]):
                gp_stroke = self._finalize_stroke(gp_data, gp_stroke, gp_points, stroke_type, new_stroke = True, gp_frame = gp_frame)
                gp_points = []
                _points.append(edge.start)

            if type(edge) == SWFCurvedEdge:
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

    def _finalize_stroke(self, gp_data, gp_stroke, gp_points, stroke_type, new_stroke = False, gp_frame = None, new_mat = None):
        # Finalize the stroke
        if stroke_type == "line":
            gp_stroke.use_cyclic = False 
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
        '''
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
        '''
        if new_stroke:
            # For SWF lines with discontinuities
            if new_mat is None:
                gp_mat = gp_data.materials[gp_stroke.material_index]
                return self._new_gp_stroke(gp_data, gp_frame, gp_mat, copy_mat = True)
            else:
                return self._new_gp_stroke(gp_data, gp_frame, new_mat)

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

    def pre_process_tags(self, tags):
        # Pull in re-sharable data (images, materials, sound)

        fill_styles = []
        line_styles = []
        sound_head = None
        mpeg_frames = b""

        for tag in tags:
            if tag.name == "End":
                if len(mpeg_frames) > 0: # There is sound
                    sound_file = open("/tmp/swf_sound.mp3", "wb") #XXX Path should probably be customizable
                    sound_file.write(mpeg_frames)
                    sound_file.close()
                    if not bpy.context.scene.sequence_editor:
                        bpy.context.scene.sequence_editor_create()
                    sound_strip = bpy.context.scene.sequence_editor.sequences.new_sound("swf_sound", "/tmp/swf_sound.mp3", 0, 1)

            elif tag.name.startswith("TagSoundStreamHead"):
                sound_head = tag

            elif tag.name == "TagSoundStreamBlock":
                if sound_head.soundFormat == 2: # MP3
                    #XXX Currently only supporting embedded MP3
                    #XXX Also assumes a single embedded sound
                    tag.complete_parse_with_header(sound_head)
                    mpeg_frames += tag.mpegFrames

            if tag.name == "DefineBitsJPEG2":
                image = Image.open(tag.bitmapData)
                img_datablock = pil_to_image(image, name = tag.name)
                img_datablock["swf_characterId"] = tag.characterId
                self.swf_data[tag.characterId] = {"data": img_datablock, "type": "image"}
        
            # Right now this doesn't account for morphing styles... ideally that could be done with a modifier
            elif tag.name.startswith("DefineShape"):
                tag.shapes._create_edge_maps()
                edge_fills = tag.shapes._fillStyles
                edge_lines = tag.shapes._lineStyles

                # Populate arrays of global fill/line styles
                for fs in edge_fills:
                    if fs not in fill_styles:
                        fill_styles.append(fs)
                for ls in edge_lines:
                    if ls not in line_styles:
                        line_styles.append(ls)

                # Populate global style combos list
                for edge_map in tag.shapes.line_edge_maps:
                    for edges in edge_map.values():
                        for edge in edges:
                            style_combo = {
                                "line_style": edge_lines[edge.line_style_idx - 1] if edge.line_style_idx > 0 else None,
                                "fill_style": edge_fills[edge.fill_style_idx - 1] if edge.fill_style_idx > 0 else None
                            }
                            if style_combo not in self.swf_style_map:
                                self.swf_style_map.append(style_combo)
                for edge_map in tag.shapes.fill_edge_maps: #XXX Partial copy pasta from above... assumes line edge maps is the same length as fill edge maps
                    for edges in edge_map.values():
                        for edge in edges:
                            style_combo = {
                                "line_style": edge_lines[edge.line_style_idx - 1] if edge.line_style_idx > 0 else None,
                                "fill_style": edge_fills[edge.fill_style_idx - 1] if edge.fill_style_idx > 0 else None
                            }
                            if style_combo not in self.swf_style_map:
                                self.swf_style_map.append(style_combo)

        # Now we create our materials
        for style_combo in self.swf_style_map:
            mat_name = "SWF Material.000"
            gp_mat = bpy.data.materials.new(mat_name)
            bpy.data.materials.create_gpencil_data(gp_mat)
            # Do the line style first
            if style_combo["line_style"] is not None:
                line_style = style_combo["line_style"]
                gp_mat.grease_pencil.color  = hex_to_rgba(hex(ColorUtils.rgb(line_style.color)))
                gp_mat["swf_linewidth"] = line_style.width
                gp_mat["swf_line_miter"] = 3.0
                gp_mat["swf_no_close"] = line_style.no_close
                gp_mat.grease_pencil.show_stroke = True
            else:
                gp_mat.grease_pencil.show_stroke = False
            # Now the fill style
            if style_combo["fill_style"] is not None:
                fill_style =style_combo["fill_style"]
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
            # Add the material to the style map
            style_combo["material"] = gp_mat

    def parse_tags(self, tags, is_sprite = False):
            # Parsing should basically look like this:
            #  * Iterate through all tags in order.
            #    * For every ShowFrame tag (type TagShowFrame, or 1), increment the current frame after processing.
            #    * All tags preceding the ShowFrame tag are potential candidates for being displayed on that previous frame.
            #    * Look for Define[Shape4,Sprite,etc] tags to dictate the actual objects added to the scene
            #      * DefineShape is another loop
            #        * In the the DefineShape4 is a property called shapes that has all the shapes
            #        * After running shapes._create_edge_maps(), there are properties, fillStyles and lineStyles that are arrays of material definitions for strokes
            #        * The shapes themselves seem to live in the records subproperty... treat them as a stream
            #          * Loop through shape records. Each StyleChangeRecord constitutes a new, disconnected GP stroke
            #    * The PlaceObject and PlaceObject2 tags (types 4 and 26, respectively) tell how and where assets are moved, based on their characterId (defined in the Define[blah] tag)
            #    * If you run into a DefineSprite tag, the whole process above gets nested. Current plan is to make a collection and place it as a collection instance

            orig_frame = bpy.context.scene.frame_current
            bpy.context.scene.frame_current = 1
            swf_object = None

            #for tag in tags:
            for i, tag in enumerate(tags):
                #print(i, tag.name)
                if tag.name == "End":
                    if is_sprite:
                        # Get first and last frames of this sprite
                        frame_start = bpy.context.scene.frame_current
                        frame_end = 0
                        for layer in swf_object.data.layers:
                            #XXX Assumes frames array is sorted by frame number
                            if layer.frames[0].frame_number < frame_start:
                                frame_start = layer.frames[0].frame_number
                            if layer.frames[-1].frame_number > frame_end:
                                frame_end = layer.frames[-1].frame_number
                        # Hacky clean-up because I think SWF assumes all sprite animations are loops
                        if frame_start != frame_end:
                            loop_modifier = swf_object.grease_pencil_modifiers.new("Cyclic Animation", "GP_TIME")
                            loop_modifier.use_keep_loop = True
                            loop_modifier.use_custom_frame_range = True
                            loop_modifier.frame_start = frame_start
                            loop_modifier.frame_end = frame_end - 1 #XXX Not sure the -1 is correct; but it made the test file play smoother

                    bpy.context.scene.frame_current = orig_frame
                    return swf_object

                if tag.name.startswith("DefineShape"): # We have a new object to add!
                    # Make a new Grease Pencil object to hold our shapes
                    gp_data = bpy.data.grease_pencils.new(tag.name + ".{0:03}".format(tag.characterId))
                    gp_data["swf_characterId"] = tag.characterId
                    # Build fill and line maps with absolute coordinates and correct style indices
                    tag.shapes._create_edge_maps()
                    line_styles = tag.shapes._lineStyles
                    fill_styles = tag.shapes._fillStyles
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
                    sprite_object = self.parse_tags(tag.tags, is_sprite = True)
                    sprite_object["swf_characterId"] = tag.characterId
                    sprite_object["swf_sprite"] = True
                    # Populate the swf_data dict with our newly imported stuff
                    self.swf_data[tag.characterId] = {"data": sprite_object, "type": "sprite"}

                if tag.name.startswith("PlaceObject"):
                    if tag.hasCharacter:
                        # Add a new character (that we've already defined with ID of characterId)
                        character = self.swf_data[tag.characterId]
                        if character["type"] == "shape":
                            if swf_object is None:
                                if not is_sprite:
                                    swf_object = bpy.data.objects.new("SWF Object", character["data"].copy())
                                    self.swf_collection.objects.link(swf_object)
                                else:
                                    swf_object = bpy.data.objects.new("SWF Sprite", character["data"].copy())
                            elif "swf_sprite" in swf_object and swf_object["swf_sprite"] == True:
                                #XXX If this PlaceObject tag happens after a sprite is placed, this creates a new SWF object. Not sure if that's the correct behavior or if we go back to the original SWF object
                                swf_object = bpy.data.objects.new("SWF Object", character["data"].copy())
                                self.swf_collection.objects.link(swf_object)

                            if len(swf_object.data.layers) == 1 and swf_object.data.layers[0].info == "Layer":
                                # Rename the layer if this is the first layer
                                swf_object.data.layers[0].info = str(tag.depth)
                                layer = swf_object.data.layers[str(tag.depth)]
                                frame = layer.frames[0]
                                if tag.hasMatrix:
                                    layer_matrix = swf_matrix_to_blender_matrix(tag.matrix)
                                    self._transform_strokes(frame.strokes, layer_matrix, swf_object.matrix_world)
                                else:
                                    layer_matrix = swf_object.matrix_world
                                self.swf_layer_matrices[tag.depth] = layer_matrix
                            elif str(tag.depth) not in swf_object.data.layers:
                                layer = swf_object.data.layers.new(str(tag.depth))
                                character["data"].layers["Layer"].frames[0].frame_number = bpy.context.scene.frame_current
                                frame = layer.frames.copy(character["data"].layers["Layer"].frames[0])
                                #XXX Hacky attempt to maintain proper sorting of layers
                                swf_object.data.layers.active_index -= 1
                                while int(layer.info) < int(swf_object.data.layers[swf_object.data.layers.active_index].info) and \
                                    swf_object.data.layers.active_index > 0:
                                    swf_object.data.layers.move(layer, "DOWN")
                                    swf_object.data.layers.active_index -= 2
                                swf_object.data.layers.active_index = len(swf_object.data.layers) - 1
                                for stroke in frame.strokes:
                                    stroke_mat = character["data"].materials[stroke.material_index]
                                    if stroke_mat.name not in swf_object.data.materials:
                                        swf_object.data.materials.append(stroke_mat)
                                    # Remap index to match updated material list
                                    stroke.material_index = {stroke_mat.name: i for i, stroke_mat in enumerate(swf_object.data.materials)}[stroke_mat.name]
                                if tag.hasMatrix:
                                    layer_matrix = swf_matrix_to_blender_matrix(tag.matrix)
                                    self._transform_strokes(frame.strokes, layer_matrix, swf_object.matrix_world)
                                else:
                                    layer_matrix = swf_object.matrix_world
                                self.swf_layer_matrices[tag.depth] = layer_matrix

                            elif str(tag.depth) in swf_object.data.layers:# and tag.hasMove:
                                # Character at given depth is removed. New character (already defined with ID of characterId) is added at given depth
                                layer = swf_object.data.layers[str(tag.depth)]
                                character["data"].layers["Layer"].frames[0].frame_number = bpy.context.scene.frame_current
                                frame = layer.frames.copy(character["data"].layers["Layer"].frames[0])
                                for stroke in frame.strokes:
                                    stroke_mat = character["data"].materials[stroke.material_index]
                                    if stroke_mat.name not in swf_object.data.materials:
                                        swf_object.data.materials.append(stroke_mat)
                                    # Remap index to match updated material list
                                    stroke.material_index = {stroke_mat.name: i for i, stroke_mat in enumerate(swf_object.data.materials)}[stroke_mat.name]
                                layer_matrix = self.swf_layer_matrices[tag.depth]
                                self._transform_strokes(frame.strokes, layer_matrix, swf_object.matrix_world)
                        elif character["type"] == "sprite":
                            # Little note: when a placed object is a sprite, it has a depth value, but since we're making that a new object in Blender, its zorder may not work well if it falls in the middle of a depth stack unless we adjust Z height of strokes.
                            swf_object = character["data"]
                            swf_object["swf_depth"] = tag.depth
                            self.swf_collection.objects.link(swf_object)
                            if hasattr(tag, "instanceName") and tag.instanceName is not None:
                                swf_object.name = tag.instanceName
                            if tag.hasMatrix:
                                self._key_transforms(swf_object, tag.matrix, depth = tag.depth)
                            #XXX TODO: Support hasCharacter == True and hasMove == True (frame replacement animation for sprite objects); need a test file

                    elif not tag.hasCharacter and tag.hasMove:
                        # Character at given depth (only one character is allowed at a given depth) has been modified
                        if "swf_sprite" not in swf_object:
                            active_layer = swf_object.data.layers[str(tag.depth)]
                            new_frame = active_layer.frames.copy(active_layer.frames[-1])
                            new_frame.frame_number = bpy.context.scene.frame_current
                            if tag.hasMatrix:
                                layer_matrix = self.swf_layer_matrices[tag.depth]
                                self._transform_strokes(new_frame.strokes, swf_object.matrix_world, layer_matrix) 
                                self._transform_strokes(new_frame.strokes, tag.matrix, swf_object.matrix_world) #XXX Would be nice if I could bake these into a single matrix
                                self.swf_layer_matrices[tag.depth] = swf_matrix_to_blender_matrix(tag.matrix)
                        elif swf_object["swf_sprite"]:
                            # Sprite objects, when placed, get object animation instead of GP frame animation
                            if tag.hasMatrix: # This should almost always be true
                                self._key_transforms(swf_object, tag.matrix, depth = tag.depth)
                        else:
                            print("Something is wrong; tried to modify an object with an swf_sprite property set to False. That should never happen.")

                    if tag.hasColorTransform:
                        #XXX Perhaps not the best approach, the HSV modifier doesn't work on GP image textures; hopefully resolves better when GP objects can have Eevee materials
                        add_color = rgb_gamma([tag.colorTransform.rAdd, tag.colorTransform.gAdd, tag.colorTransform.bAdd], 2.2)
                        mix_factor = 1.0 - (tag.colorTransform.rMult / 255) #XXX Assumes uniform mixing for R, G, and B
                        swf_object.data.layers[str(tag.depth)].tint_color = add_color 
                        swf_object.data.layers[str(tag.depth)].tint_factor = 1.0
                        materials = []
                        for stroke in swf_object.data.layers[str(tag.depth)].frames[-1].strokes:
                            if stroke.material_index not in materials:
                                materials.append(stroke.material_index)
                        for mat in materials:
                            swf_object.data.materials[mat].grease_pencil.mix_factor = mix_factor

                if tag.name == "RemoveObject2":
                    # Insert a blank frame in the given layer at the current frame
                    swf_object.data.layers[str(tag.depth)].frames.new(bpy.context.scene.frame_current)
                
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
            else:
                camera_collection = bpy.data.collections[bpy.data.collections.find("Camera")]
                camera_collection.name = "SWF Camera"
                bpy.context.scene.collection.children.unlink(camera_collection)
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

        # Create a collection to hold any SWF objects
        self.swf_collection = bpy.data.collections.new("SWF Objects")
        bpy.context.scene.collection.children.link(self.swf_collection)
        self.swf_collection.children.link(camera_collection)

        self.pre_process_tags(swf.tags) #XXX This means we're digging through the whole SWF twice, but it should make it easier to parse

        self.parse_tags(swf.tags)

        return {"FINISHED"}
