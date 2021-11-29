import bpy


# Local imports
from .globals import *
from .swf.tag import TagSetBackgroundColor
from .swf.utils import ColorUtils


def hex_to_rgb(value):
    gamma = 2.2
    value = value.lstrip('#')
    lv = len(value)
    fin = list(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    r = pow(fin[1] / 255, gamma)
    g = pow(fin[2] / 255, gamma)
    b = pow(fin[0] / 255, gamma)
    fin.clear()
    fin.append(r)
    fin.append(g)
    fin.append(b)
    return tuple(fin)


def hex_to_rgba(value):
    rgb = hex_to_rgb(value)
    rgba = list(rgb)
    rgba.append(1.0) # Just set alpha to 1
    return tuple(rgba)


def build_world(swfdata):
    # Divide by 20 because SWF units are in "twips", 1/20 of a pixel
    width = (swfdata.header.frame_size.xmax - swfdata.header.frame_size.xmin) / PIXELS_PER_TWIP
    height = (swfdata.header.frame_size.ymax - swfdata.header.frame_size.ymin) / PIXELS_PER_TWIP

    # Background color (loops should result in just one tag)
    bg_tag = [x for x in swfdata.all_tags_of_type(TagSetBackgroundColor)]

    #XXX Assume an orthographic camera because taking perspective into account when converting pixels to real units is hard
    bpy.context.scene.camera.data.type = "ORTHO"
    bpy.context.scene.camera.data.ortho_scale = max([width, height]) / PIXELS_PER_METER

    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.fps = swfdata.header.frame_rate
    bpy.context.scene.frame_end = swfdata.header.frame_count
    bpy.context.scene.world.color = hex_to_rgb(ColorUtils.to_rgb_string(bg_tag[0].color)) #XXX to_rgb_string seems to return brg instead of rgb
    bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = hex_to_rgba(ColorUtils.to_rgb_string(bg_tag[0].color))

    #print(len(swfdata.tags))
