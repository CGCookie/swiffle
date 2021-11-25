import bpy
import os


# Local imports
from . import global_vars


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


class SWF_OT_test_operator(bpy.types.Operator):
    bl_idname = "swf.test_operator"
    bl_label = "Test SWF Import"
    bl_description = "This operator tries to use pyswf to import."
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .lib.swf.movie import SWF
        from .lib.swf.tag import TagSetBackgroundColor
        from .lib.swf.utils import ColorUtils
        testfile = open(os.path.abspath(os.path.dirname(__file__) + "/test/bumble-bee1.swf"), "rb")
        testswf = SWF(testfile)
        print(testswf)
        # Divide by 20 because SWF units are in "twips", 1/20 of a pixel
        width = (testswf.header.frame_size.xmax - testswf.header.frame_size.xmin) / 20
        height = (testswf.header.frame_size.ymax - testswf.header.frame_size.ymin) / 20

        # Background color (loops should result in just one tag)
        bg_tag = [x for x in testswf.all_tags_of_type(TagSetBackgroundColor)]

        bpy.context.scene.render.resolution_x = width
        bpy.context.scene.render.resolution_y = height
        bpy.context.scene.render.fps = testswf.header.frame_rate
        bpy.context.scene.frame_end = testswf.header.frame_count
        bpy.context.scene.world.color = hex_to_rgb(ColorUtils.to_rgb_string(bg_tag[0].color)) #XXX to_rgb_string seems to return brg instead of rgb
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = hex_to_rgba(ColorUtils.to_rgb_string(bg_tag[0].color))

        print(len(testswf.tags))

        # Here's a dumb idea... use pyswf's built-in convert to SVG function... then import that using Blender's SVG importer
        from .lib.swf.export import SVGExporter
        svg_exporter = SVGExporter()
        testsvg = testswf.export(svg_exporter)
        # Temp output
        tmpout_path = "/tmp/swfimport.svg"

        open(tmpout_path, "wb").write(testsvg.read())
        #bpy.ops.wm.gpencil_import_svg(filepath=tmpout_path, scale=100, resolution=100) #XXX This seems so not be functional
        bpy.ops.import_curve.svg(filepath=tmpout_path) # Then convert to Grease Pencil. Not ideal, but it kind of works

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
