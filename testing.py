import os
from math import isclose

from lib.swf.movie import SWF

def load_swf(filepath):
    f = open(filepath, "rb")
    swf = SWF(f)
    #print(swf)
    f.close()
    return swf



def close_points(p1, p2):
    if isclose(p1[0], p2[0], rel_tol=1e-5, abs_tol=0.003) and isclose(p1[1], p2[1], rel_tol=1e-5, abs_tol=0.003):
        return True
    else:
        return False


def show_edge_maps(edge_maps):
    set_number = 0
    for em in edge_maps:
        print("Set", set_number, " - Length:", len(em))
        for key, value in em.items():
            print("Edge Map Index:", key)
            last_edge = None
            for edge in value:
                if last_edge is not None and not (close_points(edge.start, last_edge.to)):
                    print("New stroke")
                print(edge)
                last_edge = edge
        set_number += 1


def show_paths_from_edge_maps(shapes):
    set_number = 0
    print("Fills")
    for em in shapes.fill_edge_maps:
        # Check for holes and collect to a separate em
        if 0 in em:
            em_holes = em.pop(0)
        else:
            em_holes = None
        print("Set", set_number, " - Length:", len(em))
        path = shapes._create_path_from_edge_map(em)
        last_edge = None
        for edge in path:
            if last_edge is not None and (
                not (close_points(edge.start, last_edge.to)) or \
                edge.line_style_idx != last_edge.line_style_idx or \
                edge.fill_style_idx != last_edge.fill_style_idx
            ):
                print("New stroke")
            print(edge)
            last_edge = edge
        # Handle holes
        print("Holes")
        if em_holes is not None:
            for edge in em_holes:
                print(edge)
        set_number += 1
    set_number = 0
    print("Lines")
    for em in shapes.line_edge_maps:
        print("Set", set_number, " - Length:", len(em))
        path = shapes._create_path_from_edge_map(em)
        last_edge = None
        for edge in path:
            if last_edge is not None and (
                not (close_points(edge.start, last_edge.to)) or \
                edge.line_style_idx != last_edge.line_style_idx or \
                edge.fill_style_idx != last_edge.fill_style_idx
            ):
                print("New stroke")
            print(edge)
            last_edge = edge
        set_number += 1


def generate_materials(tags):
    fill_styles = []
    line_styles = []
    style_combos = []

    for tag in tags:
        if tag.name.startswith("DefineShape"):
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

            print("Number of fills:", len(edge_fills))
            print("Number of lines:", len(edge_lines))
            for edge_map in tag.shapes.line_edge_maps:
                for edges in edge_map.values():
                    for edge in edges:
                        print("Line indices (fill, line):", edge.fill_style_idx, edge.line_style_idx)
                        style_combo = {
                            "line_style": edge_lines[edge.line_style_idx - 1] if edge.line_style_idx > 0 else None,
                            "fill_style": edge_fills[edge.fill_style_idx - 1] if edge.fill_style_idx > 0 else None
                        }
                        print("Line", style_combo["line_style"])
                        print("Fill", style_combo["fill_style"])
                        if style_combo not in style_combos:
                            style_combos.append(style_combo)
            for edge_map in tag.shapes.fill_edge_maps: #XXX Partial copy pasta from above... assumes line edge maps is the same length as fill edge maps
                for edges in edge_map.values():
                    for edge in edges:
                        print("Fill indices (fill, line):", edge.fill_style_idx, edge.line_style_idx)
                        style_combo = {
                            "line_style": edge_lines[edge.line_style_idx - 1] if edge.line_style_idx > 0 else None,
                            "fill_style": edge_fills[edge.fill_style_idx - 1] if edge.fill_style_idx > 0 else None
                        }
                        print("Line", style_combo["line_style"])
                        print("Fill", style_combo["fill_style"])
                        if style_combo not in style_combos:
                            style_combos.append(style_combo)
            print("Style Combos so far:")
            for i, combo in enumerate(style_combos):
                print(i)
                print("Line Style:", combo["line_style"])
                print("Fill Style:", combo["fill_style"])

    # Output
    print("Fills")
    for fs in fill_styles:
        print(fs)
    print("Lines")
    for ls in line_styles:
        print(ls)
    print("Combos")
    for i, combo in enumerate(style_combos):
        print(i)
        print("Line Style:", combo["line_style"])
        print("Fill Style:", combo["fill_style"])

# Single frame of a drawn character bust with gradients and textures
testfile = os.path.abspath("./test/tradigital_animate_cc/10/completed/ch10-solid_drawing-closer_look-COMPLETED.swf")
faceswf = load_swf(testfile)

# Animated scene with audio
testfile = os.path.abspath("./test/tradigital_animate_cc/9/completed/ch9-real_world-finger_tapping-COMPLETED.swf")
tapswf = load_swf(testfile)

# Somewhat contrived simple scene of a bee
testfile = os.path.abspath("./test/bumble-bee1.swf")
beeswf = load_swf(testfile)

# Stupidly simple test
testfile = os.path.abspath("./test/star.swf")
starswf = load_swf(testfile)

# Gradient and line drawing test
testfile = os.path.abspath("./test/DefineShape4.swf")
gradswf = load_swf(testfile)

# Simple object animation
testfile = os.path.abspath("./test/wheel.swf")
wheelswf = load_swf(testfile)

# Simple PlaceObject test with sprites
testfile = os.path.abspath("./test/placeobject3.swf")
placeswf = load_swf(testfile)
