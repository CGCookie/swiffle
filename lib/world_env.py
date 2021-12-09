import bpy


# Local imports
from .globals import *
from .swf.tag import TagSetBackgroundColor
from .swf.utils import ColorUtils


def rgb_gamma(rgb, gamma):
    r = pow(rgb[0] / 255, gamma)
    g = pow(rgb[1] / 255, gamma)
    b = pow(rgb[2] / 255, gamma)
    rgb.clear()
    rgb.append(r)
    rgb.append(g)
    rgb.append(b)
    return tuple(rgb)


def hex_to_rgb(value):
    # Quick fix since we don't always get consistently-lengthed hex strings
    if len(value) < 8:
        value = "0x" + value[2:].rjust(6, "0")
    gamma = 2.2
    value = value[2:]
    lv = len(value)
    fin = list(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return rgb_gamma(fin, gamma)


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
    camera = bpy.context.scene.camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max([width, height]) / PIXELS_PER_METER
    camera.data.shift_x = 0.5
    camera.data.shift_y = -(min([width, height]) * 0.5) / max([width, height])
    camera.location = [0, 0, 10]
    camera.rotation_euler = [0, 0, 0]

    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.fps = swfdata.header.frame_rate
    bpy.context.scene.frame_end = swfdata.header.frame_count
    bpy.context.scene.world.color = hex_to_rgb(hex(ColorUtils.rgb(bg_tag[0].color)))
    bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = hex_to_rgba(hex(ColorUtils.rgb(bg_tag[0].color)))

    #print(len(swfdata.tags))
