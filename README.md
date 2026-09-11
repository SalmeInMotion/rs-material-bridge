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

## Supported versions

Whatever your Redshift supports, minus one floor of our own.

The installer reads the host plugins your Redshift actually ships
(`<Redshift>/Plugins/Houdini/*` and `.../C4D/*`) instead of carrying a
version table that goes stale — Maxon's published docs lagged a release
behind their own installer while this was written, so the installation on
disk is the only source worth trusting.

- **Houdini** — every series Redshift has a plugin for (19.0 through 22.0
  with Redshift 2026).
- **Cinema 4D** — every version Redshift has a plugin for, from **2024**
  up. 2023 is excluded on our side: the node-graph API this tool uses is
  only known-good from 2024 on. R25/S26 are gone from Redshift itself.

Verified by the author: **Houdini 21.0.700 and 22.0.368**, **Cinema 4D
2024.4 and 2026**. The rest share the same APIs but have not been
exercised — please report anything odd.

If no Redshift installation is found, the installer says so and falls back
to a conservative built-in list.

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

### How the Houdini preference folder is found

No path is assumed: the installer asks the system, in this order.

1. **`HOUDINI_USER_PREF_DIR`** if set (studios usually do) — it overrides
   everything else, so those folders are the only ones preselected. The
   `__HVER__` token is expanded.
2. **The real Documents folder, read from the Windows registry.** This is
   already localized (`Documentos`, `Dokumente`, ...) and already has any
   OneDrive redirection resolved, so no folder name is ever guessed.
3. The home folder and `~/Documents`, for setups using `$HOME`.
4. Every OneDrive root (`OneDrive`, `OneDriveConsumer`,
   `OneDriveCommercial`, `~/OneDrive`) **and each of its immediate
   subfolders**, whatever they are named.
5. On macOS, `~/Library/Preferences/houdini`.

Several `houdiniXX.X` folders usually exist at once — redirection leaves
empty decoys behind, and old locations keep stale copies. Candidates are
ranked by whether they hold loose files (a live folder does; a leftover
holds only empty subfolders, sometimes even an empty `packages`), then by
preference markers, then by how recently they were written. Only the best
of each version is preselected; the rest stay listed and selectable.

### Commands

- **Copy RS Material** — Houdini: select one or more `redshift_vopnet`
  nodes (or any node inside one). C4D: select the materials in the
  Material Manager. Everything selected is copied in one go.
- **Paste RS Material** — rebuilds them all (Houdini: under `/mat`, laid
  out in a row from the network editor cursor; C4D: into the active
  document). A material that fails to rebuild is reported and skipped
  instead of aborting the rest.
- **Refresh Node Inventory** — rarely needed, every Copy already does it.

### Developer setup

To work on the code without reinstalling, link instead of copying — the
installer detects links and leaves them alone:

```powershell
New-Item -ItemType Junction -Path "<c4d prefs>\library\scripts\rs-material-bridge" -Target "<repo>\c4d"
```

## Interchange format (v2)

```json
{
  "format": "rs-material-bridge",
  "version": 2,
  "source_app": "houdini",
  "materials": [{
    "name": "my_mat",
    "nodes": [
      {"key": "n0", "class": "openpbrmaterial", "name": "OpenPBR1",
       "params": {"base_color": [0.5, 0.1, 0.1], "specular_roughness": 0.4}},
      {"key": "n1", "class": "texturesampler", "name": "DiffTex",
       "params": {"tex0.path": "C:/tex/diff.png", "tex0.colorspace": "sRGB"}},
      {"key": "n2", "class": "rsramp", "name": "Ramp",
       "params": {"ramp": {"_kind": "ramp", "color": true, "knots": [
         {"pos": 0.0, "value": [0, 0, 0], "interp": "linear"},
         {"pos": 1.0, "value": [1, 1, 1], "interp": "smooth"}]}}}
    ],
    "connections": [
      {"src": "n1", "src_port": "outcolor", "dst": "n0", "dst_port": "base_color"}
    ],
    "outputs": {"surface": "n0"}
  }],
  "warnings": []
}
```

Version 2 replaced the single `material` key with the `materials` list
(multi-copy) and added the ramp value type. Readers still accept the old
single-material key; a clipboard written by a *newer* version is refused
with a clear message rather than half-read.

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

### Preferences — default path

**RS Bridge > Preferences...** in Cinema 4D sets a folder the bridge is
allowed to write into, stored in
`%USERPROFILE%\.rs_material_bridge\preferences.json`.

It is used for textures that are not files. Materials from the **Asset
Browser** keep their textures inside an asset database, under a mangled id
that means nothing outside Cinema 4D, so such a material transfers
complete but renders untextured. With a default path set, those textures
are written out as ordinary files and the material points at them:

```
<default path>/C4D - Asset Browser/<categories>/<material>/<texture>.png
```

The categories and the real file names come from the asset database, so
the result is navigable rather than a pile of hashes — e.g.
`C4D - Asset Browser/Textures/Surfaces/Redshift/Fencing/Fence Chicken
Wire 01 .../mxn_fence_chicken_wire-01_4k_opacity.png`. Files already
written are not copied again.

Without a default path the material still works: the textures point into
Cinema 4D's asset cache, with a warning saying so — that cache is not
meant to be depended on.

### Scene units

Lengths are stored in scene units and the two applications disagree on
what a unit is — Cinema 4D defaults to centimetres, Houdini works in
metres. A displacement of `0.25` therefore arrives a hundred times too
strong unless it is converted.

Each copy records how many metres one of its units is worth, and the
paste rescales the parameters that genuinely are lengths (displacement
scale, subsurface radius), reporting the factor and exactly what it
touched. Parameters that merely look like lengths are left alone:
rescaling the wrong one is worse than rescaling none.

Two settings in `preferences.json` govern it:

| Key | Meaning |
|---|---|
| `convert_units` | set to `false` to transfer lengths verbatim |
| `houdini_meters_per_unit` | override Houdini's reported unit length (read from `unitlength`, normally 1 metre) |

**If lengths still land wrong, check Houdini's Unit Length first.** The
conversion honours what each application *declares* its units to be, not
how big the geometry happens to be. Modelling at centimetre numbers in a
scene that says "1 unit = 1 metre" will convert the wrong way — set
Houdini's unit length to match how you actually work, or turn
`convert_units` off.

### Ramps

Ramps travel with their knots (position, colour/value) intact. Because the
two applications name their interpolation modes differently, the format
carries a neutral vocabulary and each side maps onto its own:

| Interchange | Cinema 4D | Houdini |
|---|---|---|
| `constant` | `none` | Constant |
| `linear` | `linearknot` | Linear |
| `cubic` | `cubicknot` (and `cubicbias`) | CatmullRom |
| `smooth` | `smoothknot` (and `blend`) | MonotoneCubic |

Houdini's Bezier / B-Spline / Hermite have no Cinema 4D counterpart and
travel as `cubic`; Cinema 4D's per-knot **bias** has no Houdini
counterpart and is dropped. Both warn rather than pass silently.

## Known limitations (v1)

- **Ramps / curves** are skipped with a warning (different representation on
  each side — planned for v2).
- OSL nodes, per-node C4D layouts, and Houdini spare parms are not carried.
- Enum parameters need no mapping table: both plugins identify the options
  by the same Redshift numbers (Houdini's dropdowns literally use "0", "1",
  "2" as their menu tokens), so they are transferred exactly. Watch the
  console warnings after a paste: every parameter that could not be matched
  or set is listed there.
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
