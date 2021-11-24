# ***** BEGIN GPL LICENSE BLOCK *****
#
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ***** END GPL LICENCE BLOCK *****


bl_info = {
    "name": "Adobe SWF format",
    "author": "Jason van Gumster (Fweeb)",
    "version": (0, 1),
    "blender": (2, 92, 0),
    "location": "File > Import-Export",
    "description": "Import-Export SWF to and from Grease Pencil objects",
    "warning": "This add-on requires installing dependencies",
    "doc_url": "",
    "tracker_url": "",
    "support": 'TESTING',
    "category": "Import-Export",
}


import bpy
import subprocess


# Local imports
from . import global_vars
global_vars.initialize()
from .install_dependencies import dependencies, install_pip, install_and_import_module, import_module
from .playground import SWF_PT_warning_panel, SWF_OT_test_operator, SWF_PT_panel


classes = (SWF_OT_test_operator,
           SWF_PT_panel)


class SWF_OT_install_dependencies(bpy.types.Operator):
    bl_idname = "preferences.swf_install_dependencies"
    bl_label = "Install dependencies"
    bl_description = ("Downloads and installs the required python packages for this add-on. "
                      "Internet connection is required. Blender may have to be started with "
                      "elevated permissions in order to install the package")
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(self, context):
        # Deactivate when dependencies have been installed
        return not global_vars.dependencies_installed

    def execute(self, context):
        try:
            install_pip()
            for dependency in dependencies:
                install_and_import_module(module_name=dependency.module,
                                          package_name=dependency.package,
                                          global_name=dependency.name)
        except (subprocess.CalledProcessError, ImportError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}

        global_vars.dependencies_installed = True

        # Register the panels, operators, etc. since dependencies are installed
        for cls in classes:
            bpy.utils.register_class(cls)

        return {"FINISHED"}


class preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        layout.operator(SWF_OT_install_dependencies.bl_idname, icon="CONSOLE")


preference_classes = (SWF_PT_warning_panel,
                      SWF_OT_install_dependencies,
                      preferences)


def register():

    for cls in preference_classes:
        bpy.utils.register_class(cls)

    try:
        for dependency in dependencies:
            import_module(module_name=dependency.module, global_name=dependency.name)
        global_vars.dependencies_installed = True
    except ModuleNotFoundError:
        # Don't register other panels, operators etc.
        return

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in preference_classes:
        bpy.utils.unregister_class(cls)

    if global_vars.dependencies_installed:
        for cls in classes:
            bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
