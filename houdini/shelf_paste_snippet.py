# Shelf tool: "RS Mat Paste"
# Rebuilds a material from the bridge clipboard into /mat.
import sys
import importlib

_DIR = r"C:\IA\Tools\C4D\rs-material-bridge\houdini"
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import rs_bridge_hou
importlib.reload(rs_bridge_hou)
rs_bridge_hou.paste_material()
