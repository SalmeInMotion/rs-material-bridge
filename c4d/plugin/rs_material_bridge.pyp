"""RS Material Bridge -- Cinema 4D menu plugin.

Registers Copy / Paste as real commands and adds an "RS Bridge" entry to
the main menu bar, so the tool is one click away instead of buried in the
Script Manager. Install with install.py, which copies this file (and the
core module next to it) into the C4D user plugins folder.

PLUGIN IDS: the ids below are Maxon's development range (1000001-1000010).
They are fine for testing but MUST be replaced with ids registered at
plugincafe.maxon.net before public distribution, or they will collide with
other developers' test plugins.
"""

import importlib
import os
import sys

import c4d
from c4d import plugins, gui

PLUGIN_ID_COPY = 1000001
PLUGIN_ID_PASTE = 1000002
PLUGIN_ID_PREFS = 1000005

CORE_NAME = "rs_bridge_c4d_core.py"
_HERE = os.path.dirname(os.path.abspath(__file__))
# Resolved separately: the plugin folder may be a link into a working copy,
# and the module then sits beside the *real* folder, not beside the link.
_REAL = os.path.dirname(os.path.realpath(__file__))

bridge = None


def _load_bridge():
    """Find and import the core module. Installed it sits next to this
    file; run from a working copy it is one level up. Every candidate is
    derived from this file's own location, so no install path is
    hardcoded."""
    global bridge
    candidates = []
    for base in (_HERE, _REAL):
        candidates.append(base)
        candidates.append(os.path.dirname(base))
    for cand in candidates:
        if not os.path.isfile(os.path.join(cand, CORE_NAME)):
            continue
        if cand not in sys.path:
            sys.path.insert(0, cand)
        try:
            import rs_bridge_c4d_core
            bridge = rs_bridge_c4d_core
            return True
        except ImportError as e:
            print("[RS Bridge] found %s in %s but could not import it: %s"
                  % (CORE_NAME, cand, e))
    return False


_load_bridge()


def _require_bridge():
    """Reload before every command, so an updated core module takes effect
    without restarting Cinema 4D and a stale copy can never run. Retries
    the search too, so a re-run installer is picked up without a restart."""
    global bridge
    if bridge is None and not _load_bridge():
        gui.MessageDialog(
            "RS Material Bridge: %s was not found near\n%s\n\n"
            "Re-run the installer." % (CORE_NAME, _HERE))
        return False
    try:
        importlib.reload(bridge)
    except Exception as e:
        print("[RS Bridge] could not reload the core module: %s" % e)
    return True


class CopyMaterialCommand(plugins.CommandData):
    def Execute(self, doc):
        if not _require_bridge():
            return True
        bridge.run_copy()
        return True

    def GetState(self, doc):
        return c4d.CMD_ENABLED


class PasteMaterialCommand(plugins.CommandData):
    def Execute(self, doc):
        if not _require_bridge():
            return True
        bridge.run_paste()
        return True

    def GetState(self, doc):
        return c4d.CMD_ENABLED


class PreferencesCommand(plugins.CommandData):
    def Execute(self, doc):
        if not _require_bridge():
            return True
        bridge.run_preferences()
        return True

    def GetState(self, doc):
        return c4d.CMD_ENABLED


def _menu_title():
    """The menu carries the version, so which build is running is visible
    at a glance instead of being something to go and check."""
    version = getattr(bridge, "TOOL_VERSION", None) if bridge else None
    return "RS Bridge %s" % version if version else "RS Bridge"


def _build_menu():
    """Insert an 'RS Bridge' menu into the main menu bar."""
    main_menu = gui.GetMenuResource("M_EDITOR")
    if main_menu is None:
        return
    # Don't add the menu twice when C4D rebuilds it (layout changes).
    for _index, value in main_menu:
        if isinstance(value, c4d.BaseContainer) and \
                value.GetString(c4d.MENURESOURCE_SUBTITLE).startswith(
                    "RS Bridge"):
            return

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, _menu_title())
    menu.InsData(c4d.MENURESOURCE_COMMAND,
                 "PLUGIN_CMD_%d" % PLUGIN_ID_COPY)
    menu.InsData(c4d.MENURESOURCE_COMMAND,
                 "PLUGIN_CMD_%d" % PLUGIN_ID_PASTE)
    separator = getattr(c4d, "MENURESOURCE_SEPARATOR", None)
    if separator is not None:
        menu.InsData(separator, True)
    menu.InsData(c4d.MENURESOURCE_COMMAND,
                 "PLUGIN_CMD_%d" % PLUGIN_ID_PREFS)

    plugins_menu = gui.SearchPluginMenuResource()
    if plugins_menu is not None:
        main_menu.InsDataAfter(c4d.MENURESOURCE_STRING, menu, plugins_menu)
    else:
        main_menu.InsData(c4d.MENURESOURCE_STRING, menu)


def PluginMessage(msg_id, data):
    if msg_id == c4d.C4DPL_BUILDMENU:
        # Anything raised here costs the whole menu silently, so a single
        # bad call can never be worth taking the entry down with it.
        try:
            _build_menu()
        except Exception as e:
            print("[RS Bridge] could not build the menu: %r" % (e,))
    return True


def _icon(name):
    path = os.path.join(_HERE, "res", name)
    if not os.path.isfile(path):
        return None
    bmp = c4d.bitmaps.BaseBitmap()
    if bmp.InitWith(path)[0] != c4d.IMAGERESULT_OK:
        return None
    return bmp


if __name__ == "__main__":
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID_COPY,
        str="Copy RS Material",
        info=0,
        icon=_icon("copy.tif"),
        help="Copy the active Redshift material to the bridge clipboard",
        dat=CopyMaterialCommand())
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID_PASTE,
        str="Paste RS Material",
        info=0,
        icon=_icon("paste.tif"),
        help="Rebuild the material held in the bridge clipboard",
        dat=PasteMaterialCommand())
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID_PREFS,
        str="RS Bridge Preferences...",
        info=0,
        icon=None,
        help="Set the folder the bridge may write extracted textures to",
        dat=PreferencesCommand())
