"""RS Material Bridge -- Paste (C4D Script Manager script).

Rebuilds a Redshift node material from the bridge clipboard file
(copied from Houdini or another C4D session) into the active document.
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
importlib.reload(rs_bridge_c4d_core)  # pick up edits without restarting C4D


def main():
    rs_bridge_c4d_core.run_paste()


if __name__ == "__main__":
    main()
