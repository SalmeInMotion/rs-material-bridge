# Shelf tool: "RS Mat Copy"
# Copies the selected Redshift material to the bridge clipboard.
import sys
import importlib

_DIR = r"C:\IA\Tools\C4D\rs-material-bridge\houdini"
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import rs_bridge_hou
importlib.reload(rs_bridge_hou)
rs_bridge_hou.copy_selected_material()
