# RS Material Bridge — beta testing guide

**Version: 0.9.0-beta.1** — thanks for testing! This tool copy/pastes
Redshift node materials between **Houdini** and **Cinema 4D**, in both
directions, rebuilding the material natively on the other side (no USD, no
proxies, fully editable result).

## What it CAN do today

- Transfer complete RS shader graphs: nodes, parameter values, texture
  paths + color spaces, node connections, and the surface / displacement /
  volume output wiring.
- Both directions: Houdini → C4D and C4D → Houdini.
- ~158 of ~162 RS node classes are portable — see
  [COMPATIBILITY.md](COMPATIBILITY.md) and the visual guide in
  [docs/node-guide.html](docs/node-guide.html).
- Warn you **at copy time** when a material uses a node that does not
  exist on the other side (after you have run Copy at least once in each
  app, which records each app's node inventory).

## What it CANNOT do yet (known limitations — don't file these)

- **Ramps / curves**: the ramp nodes travel, but knot/curve values do not
  — they reset to defaults on paste. This is the top item on the roadmap.
- **OSL**: the node travels with its source best-effort; dynamically
  created ports may not reconnect.
- **Animated texture sequences**: static texture paths travel; C4D's
  sequence settings (frame range, rate, loops) and Houdini `$F` tokens are
  not translated.
- **Texture repathing**: paths are copied verbatim. If the target machine
  can't see the same paths, textures will be missing (the material still
  builds).
- **Scene-side data**: user data attribute *names* travel (e.g.
  "RSObjectID"), but the bridge cannot create the object tags/attributes
  that feed them in the target scene.
- **Enums**: raw values are transferred; in rare cases a menu setting may
  not match — please report these, they are cheap to fix.
- C4D pasted nodes are not auto-arranged (use Node Editor > Arrange).
- 4 node classes are app-exclusive and skipped with a warning:
  `c4dhairattribute`, `reference` (C4D) / `shadermerge`, `vopswitch`
  (Houdini).

## Install

Requirements: **Houdini 20.5 or 21.0**, and/or **Cinema 4D 2024, 2025 or
2026**, with Redshift installed in each.

Deliberately out of scope: Houdini 22 (Redshift has no plugin for it yet)
and Cinema 4D R25 / S26 (Redshift dropped them in 2026.0.0). The installer
lists those with the reason rather than hiding them.

1. Put this folder wherever you want to keep it.
2. Double-click **`install.bat`** (Windows) or run `python install.py`.
3. Confirm the detected Houdini / Cinema 4D versions, press **Install**.
4. Restart the applications.

Both apps get an **RS Bridge** menu in the top menu bar. The installer only
writes inside your Houdini / C4D preference folders, and **Uninstall**
removes exactly what it added.

If the installer can't find your installation, use "Browse for another
folder..." and point it at the preference folder (Houdini: the folder named
`houdini20.5`, `houdini21.0`... in Documents or your home folder; C4D: the
folder inside `AppData/Roaming/Maxon`). **If that happens, please tell me —
detection failing is itself a bug worth reporting.**

## Workflow

1. Select a Redshift material (C4D: in the Material Manager; Houdini: the
   `redshift_vopnet` or any node inside it).
2. **RS Bridge > Copy RS Material** in the source app.
3. **RS Bridge > Paste RS Material** in the target app.

The transfer goes through `~/.rs_material_bridge/clipboard.json` — both
apps on the same machine. Cross-machine: copy that file over (or point
both apps' `RS_MATERIAL_BRIDGE_DIR` environment variable to a shared
folder).

## How to report issues

Every Copy/Paste prints a `[RS Bridge]` report to the app's console
(C4D: Extensions > Console; Houdini: the terminal / Python Shell).
For any issue, please send:

1. What you did and what you expected.
2. The **full console output** (especially `warning:` lines).
3. The file `~/.rs_material_bridge/clipboard.json` (it contains the
   serialized material — that's the whole bug in one file).
4. Your Houdini / C4D / Redshift versions and OS.

A paste that *silently* produces wrong values (no warning, but a
parameter differs from the source) is the most valuable bug you can find
— please compare a couple of materials side by side.
