import bpy
import os


# Local imports
from . import global_vars


class EXAMPLE_OT_dummy_operator(bpy.types.Operator):
    bl_idname = "example.dummy_operator"
    bl_label = "Dummy Operator"
    bl_description = "This operator tries to use pyswf."
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .lib.swf.movie import SWF
        testfile = open(os.path.abspath(os.path.dirname(__file__) + "/test/rectangle.swf"), "rb")
        print(SWF(testfile))
        return {"FINISHED"}


class EXAMPLE_PT_panel(bpy.types.Panel):
    bl_label = "Example Panel"
    bl_category = "Example Tab"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        layout.operator(EXAMPLE_OT_dummy_operator.bl_idname)


class EXAMPLE_PT_warning_panel(bpy.types.Panel):
    bl_label = "Example Warning"
    bl_category = "Example Tab"
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
