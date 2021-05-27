# Import/Export SWF

This is an add-on for importing and exporting Adobe SWF files to and from Blender Grease Pencil objects.

## Installation Dependencies

This add-on requires that you install a few Python modules in order for it to work. There's a handy button in the add-on's Preferences to install them for you. Clicking that button installs the following two modules where Blender's Python interpreter can see them:

  * lxml
  * pylzma

*(Note: If you get an UnsupportedPlatformWarning installing pylzma, it's probably because you're missing headers for your version of Python. This typically involves copying the Python 3.x [whichever Python Blender was built with] headers into Blender's Python path... this will likely need to be something to resolve prior to a proper release.)*

## Known Issues

  * Automatically installing pyLZMA requires Python header files in Blender's Python's include path.

## Attribution

Portions of code were used from the following:

  * [Install Dependencies](https://github.com/robertguetzkow/blender-python-examples/) (GPL 3.0) by Robert Gützkow
  * [PYSWF](https://github.com/timknip/pyswf) (MIT license) by Tim Knip
