# Changelog

## 0.9.0-beta.2 — 2026-09-09

Everything reported in the first beta round, plus the groundwork that fell
out of chasing it.

### Fixed

- **Every checkbox arrived ticked** when copying from Cinema 4D — "Thin
  walled" included, which visibly changes a transmissive material. The
  exporter was asking whether the value object existed rather than what it
  held, which is always true. *(Thanks to the first beta report; this is
  exactly the kind of silent wrong value that is hardest to spot.)*
- The Cinema 4D menu ran a **stale copy of the code** after an update, so
  fixes appeared not to work. It now always uses the current version, and
  updating no longer needs a Cinema 4D restart.
- **False warnings**: dropdown values transfer exactly (both applications
  identify the options by the same Redshift numbers), but every one of
  them was being reported as needing verification — nine per material.
  Only genuine guesses are reported now.
- Texture paths on network shares (`\\server\...`) were corrupted, as were
  paths containing `#`, `%` or spaces.
- Ten warnings per material about the internal parameters behind a Houdini
  ramp, which duplicate the ramp itself.

### Added

- **Ramps travel.** Knot positions and colours transfer exactly in both
  directions; the four common interpolation modes map across. Houdini's
  Bezier / B-Spline / Hermite and Cinema 4D's per-knot bias have no
  counterpart and are reported rather than dropped silently.
- **Multi-copy.** Every selected material moves in one go — the Material
  Manager selection in Cinema 4D, the selected builders in Houdini.
- **Installer** (`install.bat` / `install.py`). Detects the installed
  versions, works out where each keeps its preferences, and adds an
  **RS Bridge** menu to both applications. Uninstall included.
- Pasted materials in Houdini are laid out in a row from the network
  editor cursor instead of stacking at the origin.
- Reports count materials, nodes and connections done vs. expected, so a
  partial paste is visible at a glance. Ctrl+Z undoes a paste in C4D.

### Changed

- Only versions your Redshift actually supports are offered; the installer
  reads that from your Redshift installation rather than a fixed list.
- Interchange format v2 (materials list, ramp values). Clipboards written
  by a newer version are refused with a clear message instead of being
  half-read.

## 0.9.0-beta.1 — 2026-07-09

First beta: Redshift node materials copy and paste between Houdini and
Cinema 4D in both directions, with a measured node compatibility list.
