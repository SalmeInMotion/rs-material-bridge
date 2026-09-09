"""RS Material Bridge -- Paste (C4D Script Manager script).

Rebuilds a Redshift node material from the bridge clipboard file
(copied from Houdini or another C4D session) into the active document.
"""

import os
import sys
import importlib

# The core module lives next to this script -- no install path is
# hardcoded, so the folder works wherever the user put it.
try:
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:  # pasted into the Console instead of run as a file
    _here = None
if _here and _here not in sys.path:
    sys.path.insert(0, _here)

try:
    import rs_bridge_c4d_core
except ImportError:
    import c4d
    c4d.gui.MessageDialog(
        "rs_bridge_c4d_core.py not found next to this script.\n"
        "Keep the whole rs-material-bridge folder together.")
    raise
importlib.reload(rs_bridge_c4d_core)  # pick up edits without restarting C4D


def main():
    rs_bridge_c4d_core.run_paste()


if __name__ == "__main__":
    main()
