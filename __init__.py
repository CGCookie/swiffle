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


bl_info = {
    "name": "Adobe SWF format",
    "author": "Jason van Gumster (Fweeb)",
    "version": (0, 1),
    "blender": (3, 0, 0),
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
from .import_swf import SWF_OT_import


classes = (SWF_OT_import,)


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

        lines = [f"This add-on requires a couple Python packages to be installed:",
                 f"  - pillow",
                 f"  - lxml",
                 f"  - pylzma",
                 f"Click the Install Dependencies button below to install them."]

        for line in lines:
            layout.label(text=line)

        layout.operator(SWF_OT_install_dependencies.bl_idname, icon="CONSOLE")


preference_classes = (SWF_OT_install_dependencies,
                      preferences)


def add_to_import_menu(self, context):
    self.layout.operator(SWF_OT_import.bl_idname, text = "Flash/Animate (.swf)")


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

    bpy.types.TOPBAR_MT_file_import.append(add_to_import_menu)


def unregister():
    for cls in preference_classes:
        bpy.utils.unregister_class(cls)

    if global_vars.dependencies_installed:
        for cls in classes:
            bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(add_to_import_menu)


if __name__ == "__main__":
    register()
