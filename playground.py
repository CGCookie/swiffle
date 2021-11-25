import bpy
import os


# Local imports
from . import global_vars
from .lib.world_env import build_world


class SWF_OT_test_operator(bpy.types.Operator):
    bl_idname = "swf.test_operator"
    bl_label = "Test SWF Import"
    bl_description = "This operator tries to use pyswf to import."
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .lib.swf.movie import SWF
        testfile = open(os.path.abspath(os.path.dirname(__file__) + "/test/bumble-bee1.swf"), "rb")
        testswf = SWF(testfile)
        print(testswf)

        build_world(testswf)

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
