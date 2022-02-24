import os

from lib.swf.movie import SWF

def load_swf(filepath):
    f = open(filepath, "rb")
    swf = SWF(f)
    #print(swf)
    f.close()
    return swf


def show_edge_maps(edge_maps):
    group_number = 0
    for em in edge_maps:
        print("Group", group_number, " - Length:", len(em))
        for key, value in em.items():
            print(key)
            for edge in value:
                print(edge)
        group_number += 1

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
