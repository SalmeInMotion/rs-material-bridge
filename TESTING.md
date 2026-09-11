# RS Material Bridge — beta testing guide

**Version: 0.9.0-beta.2** — thanks for testing! This tool copy/pastes
Redshift node materials between **Houdini** and **Cinema 4D**, in both
directions, rebuilding the material natively on the other side (no USD, no
proxies, fully editable result).

## Coming from the first beta? Remove it first

The first beta was installed by hand, so nothing knows how to clean it up
— and two copies fighting over the same clipboard would waste your time
chasing bugs that are not there. Before installing this one:

1. **Houdini**: delete the two shelf tools you created (right-click the
   tool > Delete Tool).
2. **Cinema 4D**: delete the folder you copied into
   `.../library/scripts/rs-material-bridge`.
3. Delete the old repository folder itself.
4. Optional but tidy: delete `%USERPROFILE%\.rs_material_bridge` — the old
   clipboard is in the previous format and would be refused anyway.

Then run the installer below. From this version on, updating is just
"run the installer again", and **Uninstall** removes everything it added.

## What changed since your report

Everything you found or asked for — see [CHANGELOG.md](CHANGELOG.md) for
the full list. The short version: the checkbox bug is fixed (it was real
and it affected every material), ramps now travel, several materials can
be copied at once, there is a proper installer with menus in both
applications, and pasted materials land where you are looking rather than
on top of each other.

Two things worth re-testing specifically: **the checkbox bug you found**
(it is your report — please confirm the fix in a real material), and
**ramps**, which are new and where the interpolation is mapped rather
than identical.

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

- **Ramp interpolation is mapped, not identical**: knot positions and
  colours transfer exactly, and the four common modes map both ways
  (step/none, linear, cubic, smooth). Houdini's Bezier, B-Spline and
  Hermite have no Cinema 4D equivalent and arrive as a smooth curve;
  Cinema 4D's per-knot *bias* has no Houdini equivalent and is dropped.
  Both cases warn.
- **Enums / dropdowns do travel correctly** (verified): both applications
  identify the options by the same Redshift numbers, so `diffuse_model`,
  `ms_mode` and friends land on the right entry.
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

Requirements: Redshift, plus **any Houdini version your Redshift has a
plugin for** (19.0-22.0 with Redshift 2026) and/or **Cinema 4D 2024 or
newer**. The installer works this out by reading your Redshift
installation, so it only ever offers combinations that can actually run.

Verified so far: Houdini 21.0.700 / 22.0.368, Cinema 4D 2024.4 / 2026.

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

1. Select **one or more** Redshift materials (C4D: in the Material
   Manager; Houdini: the `redshift_vopnet` nodes, or any node inside one).
2. **RS Bridge > Copy RS Material** in the source app.
3. **RS Bridge > Paste RS Material** in the target app.

Everything selected travels in one go. In Houdini the pasted materials
are laid out in a row starting where you last had the network editor
cursor, rather than piling up at the origin.

The transfer goes through `~/.rs_material_bridge/clipboard.json` — both
apps on the same machine. Cross-machine: copy that file over (or point
both apps' `RS_MATERIAL_BRIDGE_DIR` environment variable to a shared
folder).

## Scene units

Cinema 4D counts in centimetres and Houdini in metres, so lengths are
converted on paste — a displacement of 0.25 cm arrives as 0.0025 rather
than a hundred times too strong. Only parameters that really are lengths
are touched (displacement scale, subsurface radius) and the report says
which. **If you spot another setting that lands the wrong size, that is
worth reporting** — it probably belongs on that list.

## Materials from the Asset Browser

Their textures are not files on disk — they live inside Cinema 4D's asset
database. Set a folder in **RS Bridge > Preferences...** and the bridge
writes them out as ordinary files, organised by the asset's own categories
and material name, so the material arrives textured. Without it the
material still transfers, but points into C4D's asset cache and says so.

## "The material arrived but the textures don't show in Houdini"

Almost always the geometry, not the material. **Houdini geometry has no UV
coordinates unless you add them**, while Cinema 4D primitives come with
them built in — so the same material looks right in C4D and flat in
Houdini. Add a **UV Project**, **UV Texture** or **UV Unwrap** SOP before
rendering, or feed the texture through a Triplanar node, which needs no
UVs at all.

Verified here with a sphere rendered twice, identical material and
texture: without a `uv` attribute it renders flat, with one the texture
maps correctly.

While you are there: Redshift in Houdini often logs *"OpenColorIO failed
instantiating monitor color spaces"*. It is harmless — it falls back to
ACEScg / sRGB and renders normally.

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
