'''
Copyright (C) 2021-2022 Orange Turbine
https://orangeturbine.com
orangeturbine@cgcookie.com

Created by Jason van Gumster

    This file is part of Swiffle.

    Swiffle is free software; you can redistribute it and/or
    modify it under the terms of the GNU General Public License
    as published by the Free Software Foundation; either version 3
    of the License, or (at your option) any later version.
   
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
   
    You should have received a copy of the GNU General Public License
    along with this program; if not, see <https://www.gnu.org/licenses/>.

'''


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


def build_world(swfdata, width, height):
    # Background color (loops should result in just one tag)
    bg_tag = [x for x in swfdata.all_tags_of_type(TagSetBackgroundColor)]

    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)
    bpy.context.scene.render.fps = int(swfdata.header.frame_rate)
    bpy.context.scene.frame_end = int(swfdata.header.frame_count)
    bpy.context.scene.world.color = hex_to_rgb(hex(ColorUtils.rgb(bg_tag[0].color)))
    bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = hex_to_rgba(hex(ColorUtils.rgb(bg_tag[0].color)))

    #print(len(swfdata.tags))
