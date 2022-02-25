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
    if isclose(p1[0], p2[0], rel_tol=1e-5) and isclose(p1[1], p2[1], rel_tol=1e-5):
        return True
    else:
        return False


def show_edge_maps(edge_maps):
    group_number = 0
    for em in edge_maps:
        print("Group", group_number, " - Length:", len(em))
        for key, value in em.items():
            print(key)
            last_edge = None
            for edge in value:
                if last_edge is not None and not (close_points(edge.start, last_edge.to)):
                    print("New stroke")
                print(edge)
                last_edge = edge
        group_number += 1


def show_paths_from_edge_maps(shapes):
    group_number = 0
    print("Fills")
    for em in shapes.fill_edge_maps:
        print("Group", group_number, " - Length:", len(em))
        path = shapes._create_path_from_edge_map(em)
        last_edge = None
        for edge in path:
            if last_edge is not None and not (close_points(edge.start, last_edge.to)):
                print("New stroke")
            print(edge)
            last_edge = edge
    print("Lines")
    for em in shapes.line_edge_maps:
        print("Group", group_number, " - Length:", len(em))
        path = shapes._create_path_from_edge_map(em)
        last_edge = None
        for edge in path:
            if last_edge is not None and not (close_points(edge.start, last_edge.to)):
                print("New stroke")
            print(edge)
            last_edge = edge


# Single frame of a drawn character bust with gradients and textures
testfile = os.path.abspath("./test/tradigital_animate_cc/10/completed/ch10-solid_drawing-closer_look-COMPLETED.swf")
faceswf = load_swf(testfile)

# Animated scene with audio
testfile = os.path.abspath("./test/tradigital_animate_cc/9/completed/ch9-real_world-finger_tapping-COMPLETED.swf")
tapswf = load_swf(testfile)

# Somewhat contrived simple scene of a bee
testfile = os.path.abspath("./test/bumble-bee1.swf")
beeswf = load_swf(testfile)

# Simple object animation
testfile = os.path.abspath("./test/wheel.swf")
wheelswf = load_swf(testfile)
