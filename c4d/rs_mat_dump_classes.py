"""RS Material Bridge -- Dump node classes (C4D Script Manager script).

Writes the list of Redshift node classes available in this C4D build to
the bridge directory, without copying any material. Normally not needed
(every Copy refreshes it automatically) -- use it only to regenerate the
compatibility report without touching a material.
"""

import os
import sys
import importlib

_FALLBACK_DIR = r"C:\IA\Tools\C4D\rs-material-bridge\c4d"

try:
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _here = _FALLBACK_DIR
for p in (_here, _FALLBACK_DIR):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import rs_bridge_c4d_core
importlib.reload(rs_bridge_c4d_core)


def main():
    import traceback
    from c4d import gui
    try:
        classes = rs_bridge_c4d_core.dump_node_classes()
    except Exception as e:
        traceback.print_exc()
        gui.MessageDialog("Class dump failed:\n%s\n\nDetails in the Console."
                          % e)
        return
    gui.MessageDialog("Dumped %d Redshift node classes to\n%s"
                      % (len(classes), rs_bridge_c4d_core.CLASSES_SELF_FILE))


if __name__ == "__main__":
    main()
