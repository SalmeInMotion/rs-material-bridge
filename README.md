# RS Material Bridge

Copy/paste Redshift node materials between **Houdini** and **Cinema 4D 2024+**
(both directions), via a JSON "clipboard" file.

Both DCCs are frontends over the same Redshift shader library, so nodes and
parameters map almost 1:1: Houdini VOP `redshift::TextureSampler` is C4D's
`com.redshift3d.redshift4c4d.nodes.core.texturesampler`, and parameter
`base_color` is the same name on both sides. The bridge serializes the shader
graph (node classes, non-default parameters, texture paths, connections,
output wiring) to a small JSON file and rebuilds it natively on the other side.

## Clipboard location

`%USERPROFILE%\.rs_material_bridge\clipboard.json`
(override with the `RS_MATERIAL_BRIDGE_DIR` environment variable).

## Setup

Put this folder anywhere you like, then run the installer:

- **Windows**: double-click **`install.bat`** (it borrows the Python inside
  Houdini or Cinema 4D if you don't have one of your own).
- **macOS / Linux, or manually**: `python install.py`.

It detects the Houdini and Cinema 4D versions installed, preselects the
preference folder each one actually uses, and lets you browse for any it
missed. Press **Install** and restart the applications: both get an
**RS Bridge** menu in the main menu bar (Houdini also gets a shelf tab).

Nothing is written outside your Houdini / C4D preference folders, no paths
are baked into the scripts, and **Uninstall** removes exactly what was
added. Concretely:

| | What the installer adds |
|---|---|
| Houdini | `<prefs>/packages/rs_material_bridge.json` — puts the module on `PYTHONPATH` and this repo's `houdini/package` on `HOUDINI_PATH` (menu + shelf) |
| Cinema 4D | `<prefs>/library/scripts/rs-material-bridge/` (Script Manager) and `<prefs>/plugins/rs-material-bridge/` (the menu plugin) |

> Houdini preference folders are easy to get wrong: OneDrive redirection can
> leave an unused `Documents/houdiniXX.X` decoy next to the real one. The
> installer scores each candidate by what it actually contains and only
> preselects the plausible one, marking the rest "unused?".

### Commands

- **Copy RS Material** — Houdini: select a `redshift_vopnet` (or any node
  inside it). C4D: select the material in the Material Manager.
- **Paste RS Material** — rebuilds the clipboard material (Houdini: under
  `/mat`; C4D: into the active document).
- **Refresh Node Inventory** — rarely needed, every Copy already does it.

### Developer setup

To work on the code without reinstalling, link instead of copying — the
installer detects links and leaves them alone:

```powershell
New-Item -ItemType Junction -Path "<c4d prefs>\library\scripts\rs-material-bridge" -Target "<repo>\c4d"
```

## Interchange format (v1)

```json
{
  "format": "rs-material-bridge",
  "version": 1,
  "source_app": "houdini",
  "material": {
    "name": "my_mat",
    "nodes": [
      {"key": "n0", "class": "openpbrmaterial", "name": "OpenPBR1",
       "params": {"base_color": [0.5, 0.1, 0.1], "specular_roughness": 0.4}},
      {"key": "n1", "class": "texturesampler", "name": "DiffTex",
       "params": {"tex0.path": "C:/tex/diff.png", "tex0.colorspace": "sRGB"}}
    ],
    "connections": [
      {"src": "n1", "src_port": "outcolor", "dst": "n0", "dst_port": "base_color"}
    ],
    "outputs": {"surface": "n0"}
  },
  "warnings": []
}
```

Conventions:

- `class` — Redshift shader class, lowercase. Houdini derives its VOP type by
  matching against all `redshift::*` types; C4D prepends
  `com.redshift3d.redshift4c4d.nodes.core.` (a `c4d_id` hint is stored when
  exporting from C4D).
- Param/port names — lowercase RS names. Nested C4D ports are dotted
  (`tex0.path`); Houdini maps those back to `tex0` / `tex0_colorSpace`.
  All name resolution is case-insensitive on both sides.
- Values — plain JSON scalars/lists; the importer converts to whatever type
  the destination port/parm expects (vector, color, `maxon.Url`, ...).

## Node compatibility — what travels and what doesn't

Only nodes whose Redshift class exists in *both* apps can travel. Most core
shading nodes do (same RS library underneath); C4D-native extras (Maxon
noise, C4D shader wrappers...) don't.

The bridge tells you in four places:

1. **At copy time**: every Copy dumps the app's real RS node inventory to
   `classes_houdini.json` / `classes_c4d.json` in the bridge directory. Once
   both dumps exist, copying a material that uses a class missing on the
   other side warns immediately ("does not exist in C4D -- will be skipped
   on paste") — C4D counts it in the summary dialog, Houdini prints it to
   the console.
2. **At paste time**: any node that could not be recreated is listed in the
   console report, along with every parameter that could not be matched.
3. **[COMPATIBILITY.md](COMPATIBILITY.md)**: the full three-way list
   (portable / C4D-only / Houdini-only), generated from the two dumps with
   `python tools/compat_report.py`. Regenerate after Redshift updates.
4. **[docs/node-guide.html](docs/node-guide.html)**: the same data as a
   searchable visual guide (status filters, categories, notes) — generated
   with `python tools/build_node_guide.py`. Keep it open while building
   materials; it will also seed the product landing page.

Classes that exist under different names in each app (e.g. `osl` in C4D is
`rsosl` in Houdini) are bridged automatically via the alias table
(`CLASS_ALIASES` in both bridge modules) and counted as portable.

## Known limitations (v1)

- **Ramps / curves** are skipped with a warning (different representation on
  each side — planned for v2).
- OSL nodes, per-node C4D layouts, and Houdini spare parms are not carried.
- Enum parameters travel as raw values; a few may need a mapping table if the
  two plugins disagree (they mostly don't — same RS core). Watch the console
  warnings after a paste: every parameter that could not be matched or set is
  listed there.
- Texture paths are copied verbatim (no repathing). Broken paths show up in
  the destination app as-is.
- C4D pastes are not auto-arranged — use the node editor's Arrange command.

## Troubleshooting

Both sides print a `[RS Bridge]` report (Houdini console / C4D Script
Console) with one line per warning: unmatched parameters, unsupported nodes,
failed connections. The C4D connection-query API differs across 2024.x point
releases; if a copy from C4D reports `connection query API returned nothing`,
grab the console output — the fallbacks in `input_sources()` need adjusting
for that build.
