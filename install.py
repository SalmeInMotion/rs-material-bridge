"""RS Material Bridge -- installer.

Double-click install.bat (Windows) or run `python install.py`. Detects the
Houdini and Cinema 4D installations on this machine, lets you confirm or
browse for them, and wires the tool in:

  Houdini  -> a package in <prefs>/packages that puts the module on
              PYTHONPATH and adds an "RS Bridge" main menu + shelf.
  Cinema4D -> scripts in <prefs>/library/scripts and a plugin in
              <prefs>/plugins that adds an "RS Bridge" main menu.

Nothing outside those preference folders is touched, no paths are baked
into the scripts, and Uninstall removes exactly what was added.

Standard library only (tkinter ships with Python and with Houdini).
"""

import json
import os
import shutil
import sys
import traceback

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None

APP_NAME = "RS Material Bridge"
PACKAGE_NAME = "rs_material_bridge"
C4D_FOLDER_NAME = "rs-material-bridge"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
HOU_MODULE_DIR = os.path.join(REPO_DIR, "houdini")
HOU_PACKAGE_DIR = os.path.join(HOU_MODULE_DIR, "package")
C4D_SRC_DIR = os.path.join(REPO_DIR, "c4d")
C4D_PLUGIN_SRC = os.path.join(C4D_SRC_DIR, "plugin")

C4D_SCRIPT_FILES = ("rs_bridge_c4d_core.py", "rs_mat_copy.py",
                    "rs_mat_paste.py", "rs_mat_dump_classes.py")


def _tool_version():
    path = os.path.join(HOU_MODULE_DIR, "rs_bridge_hou.py")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TOOL_VERSION"):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return "?"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _home():
    return os.path.expanduser("~")


def _candidate_doc_dirs():
    """Places Houdini preference folders live. Documents may be redirected
    by OneDrive, in which case Houdini falls back to the home folder --
    both are checked, plus any OneDrive Documents folder present."""
    dirs = [_home(), os.path.join(_home(), "Documents")]
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        base = os.environ.get(key)
        if base:
            dirs.append(os.path.join(base, "Documents"))
    if sys.platform == "darwin":
        dirs.append(os.path.join(_home(), "Library", "Preferences",
                                 "houdini"))
    return [d for d in dirs if os.path.isdir(d)]


def _houdini_pref_score(path):
    """How much a folder looks like the preference folder Houdini really
    uses. Several can exist at once (OneDrive redirects Documents, leaving
    empty decoys behind), so the fullest and most recent one wins."""
    score = 0
    for marker, points in (("houdini.env", 3), ("packages", 3),
                           ("toolbar", 2), ("desktop", 1), ("config", 1)):
        if os.path.exists(os.path.join(path, marker)):
            score += points
    try:
        score += min(int(os.path.getmtime(path) / 86400 / 365), 0) + 0
    except OSError:
        pass
    return score


def find_houdini_prefs():
    """Return [(label, path, preselect)] of Houdini preference folders,
    newest version first, with only the most plausible folder of each
    version preselected."""
    found = {}
    for parent in _candidate_doc_dirs():
        try:
            entries = os.listdir(parent)
        except OSError:
            continue
        for name in entries:
            low = name.lower()
            if not low.startswith("houdini"):
                continue
            ver = name[len("houdini"):]
            if not ver or not ver[0].isdigit():
                continue
            path = os.path.join(parent, name)
            if os.path.isdir(path):
                found.setdefault(os.path.normcase(path), (ver, path))

    def ver_key(ver):
        try:
            return [int(p) for p in ver.split(".")]
        except ValueError:
            return [0]

    by_version = {}
    for ver, path in found.values():
        by_version.setdefault(ver, []).append(path)

    out = []
    for ver in sorted(by_version, key=ver_key, reverse=True):
        paths = sorted(by_version[ver], key=_houdini_pref_score,
                       reverse=True)
        for i, path in enumerate(paths):
            out.append(("Houdini %s" % ver, path, i == 0))
    return out


def find_c4d_prefs():
    """Return [(label, path)] of Cinema 4D preference folders."""
    roots = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(os.path.join(appdata, "Maxon"))
    roots.append(os.path.join(_home(), "Library", "Preferences", "Maxon"))

    found = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            if "cinema 4d" not in name.lower():
                continue
            if not os.path.isdir(os.path.join(path, "library")):
                continue
            label = name.replace("Maxon Cinema 4D ", "Cinema 4D ")
            label = label.split("_")[0]
            found.setdefault(os.path.normcase(path), (label, path, True))
    return sorted(found.values(), key=lambda i: i[0], reverse=True)


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

def _pkg_file(prefs):
    return os.path.join(prefs, "packages", PACKAGE_NAME + ".json")


def install_houdini(prefs, log):
    pkg_dir = os.path.join(prefs, "packages")
    os.makedirs(pkg_dir, exist_ok=True)
    package = {
        "env": [
            {"RS_MATERIAL_BRIDGE": REPO_DIR.replace("\\", "/")},
            {"PYTHONPATH": {
                "value": HOU_MODULE_DIR.replace("\\", "/"),
                "method": "prepend"}},
        ],
        "path": "$RS_MATERIAL_BRIDGE/houdini/package",
    }
    target = _pkg_file(prefs)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(package, f, indent=4)
    log("Houdini: wrote %s" % target)
    log("         menu 'RS Bridge' + shelf tab will appear on restart")
    return True


def uninstall_houdini(prefs, log):
    target = _pkg_file(prefs)
    if os.path.isfile(target):
        os.remove(target)
        log("Houdini: removed %s" % target)
        return True
    log("Houdini: nothing to remove in %s" % prefs)
    return False


def _c4d_script_dir(prefs):
    return os.path.join(prefs, "library", "scripts", C4D_FOLDER_NAME)


def _c4d_plugin_dir(prefs):
    return os.path.join(prefs, "plugins", C4D_FOLDER_NAME)


def install_c4d(prefs, log, with_menu=True):
    dest = _c4d_script_dir(prefs)
    if os.path.islink(dest) or (os.path.isdir(dest) and
                                not os.path.isfile(
                                    os.path.join(dest, "__installed__"))):
        # A junction/symlink (developer setup) or a previous copy: leave
        # links alone, refresh copies.
        if os.path.islink(dest):
            log("C4D: '%s' is a link, left untouched" % dest)
        else:
            shutil.rmtree(dest, ignore_errors=True)
    if not os.path.islink(dest):
        os.makedirs(dest, exist_ok=True)
        for name in C4D_SCRIPT_FILES:
            src = os.path.join(C4D_SRC_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(dest, name))
        with open(os.path.join(dest, "__installed__"), "w",
                  encoding="utf-8") as f:
            f.write("installed by %s installer\n" % APP_NAME)
        log("C4D: scripts -> %s" % dest)

    if with_menu:
        pdest = _c4d_plugin_dir(prefs)
        if os.path.isdir(pdest) and not os.path.islink(pdest):
            shutil.rmtree(pdest, ignore_errors=True)
        if not os.path.islink(pdest):
            os.makedirs(pdest, exist_ok=True)
            for name in os.listdir(C4D_PLUGIN_SRC):
                src = os.path.join(C4D_PLUGIN_SRC, name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(pdest, name))
            # The plugin imports the core module from next to itself.
            shutil.copy2(os.path.join(C4D_SRC_DIR, "rs_bridge_c4d_core.py"),
                         os.path.join(pdest, "rs_bridge_c4d_core.py"))
            log("C4D: menu plugin -> %s" % pdest)
            log("     menu 'RS Bridge' will appear on restart")
    return True


def uninstall_c4d(prefs, log):
    removed = False
    for path in (_c4d_script_dir(prefs), _c4d_plugin_dir(prefs)):
        if os.path.islink(path):
            log("C4D: '%s' is a link, left untouched" % path)
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log("C4D: removed %s" % path)
            removed = True
    if not removed:
        log("C4D: nothing to remove in %s" % prefs)
    return removed


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class InstallerUI(object):
    def __init__(self, root):
        self.root = root
        root.title("%s %s -- Installer" % (APP_NAME, _tool_version()))
        root.minsize(720, 460)

        frm = ttk.Frame(root, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=APP_NAME,
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frm, text="Copy and paste Redshift materials between "
                            "Houdini and Cinema 4D.\nPick the versions to "
                            "set up, then press Install.",
                  justify="left").pack(anchor="w", pady=(2, 12))

        self.hou_rows = self._app_section(
            frm, "Houdini", find_houdini_prefs(),
            "No Houdini preference folder found -- browse for e.g. "
            "Documents/houdini20.5")
        self.c4d_rows = self._app_section(
            frm, "Cinema 4D", find_c4d_prefs(),
            "No Cinema 4D preference folder found -- browse for the folder "
            "inside AppData/Roaming/Maxon")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 8))
        ttk.Button(btns, text="Install",
                   command=self.do_install).pack(side="left")
        ttk.Button(btns, text="Uninstall",
                   command=self.do_uninstall).pack(side="left", padx=6)
        ttk.Button(btns, text="Close",
                   command=root.destroy).pack(side="right")

        self.log_box = tk.Text(frm, height=11, wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log("Installing from: %s" % REPO_DIR)
        self.log("Nothing is written outside your Houdini / C4D preference "
                 "folders.")

    def _app_section(self, parent, title, found, empty_hint):
        box = ttk.LabelFrame(parent, text=title, padding=10)
        box.pack(fill="x", pady=5)
        rows = []
        if found:
            for label, path, preselect in found:
                var = tk.BooleanVar(value=preselect)
                row = ttk.Frame(box)
                row.pack(fill="x", pady=1)
                ttk.Checkbutton(row, text=label, variable=var,
                                width=18).pack(side="left")
                pvar = tk.StringVar(value=path)
                ttk.Entry(row, textvariable=pvar).pack(
                    side="left", fill="x", expand=True, padx=(0, 6))
                if not preselect:
                    ttk.Label(row, text="unused?",
                              foreground="#888").pack(side="left")
                rows.append((var, pvar))
        else:
            ttk.Label(box, text=empty_hint, foreground="#a33").pack(
                anchor="w", pady=(0, 6))

        add = ttk.Frame(box)
        add.pack(fill="x", pady=(6, 0))
        ttk.Button(add, text="Browse for another folder...",
                   command=lambda: self._browse(box, rows)).pack(side="left")
        return rows

    def _browse(self, box, rows):
        path = filedialog.askdirectory(title="Select the preference folder")
        if not path:
            return
        var = tk.BooleanVar(value=True)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=1, before=box.winfo_children()[-1])
        ttk.Checkbutton(row, text="custom", variable=var,
                        width=18).pack(side="left")
        pvar = tk.StringVar(value=path)
        ttk.Entry(row, textvariable=pvar).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        rows.append((var, pvar))

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.root.update_idletasks()

    def _selected(self, rows):
        return [p.get().strip() for on, p in rows
                if on.get() and p.get().strip()]

    def _run(self, hou_fn, c4d_fn, verb):
        hous = self._selected(self.hou_rows)
        c4ds = self._selected(self.c4d_rows)
        if not hous and not c4ds:
            messagebox.showwarning(APP_NAME, "Nothing selected.")
            return
        self.log("")
        self.log("--- %s ---" % verb)
        ok = 0
        for prefs in hous:
            try:
                hou_fn(prefs, self.log)
                ok += 1
            except Exception as e:
                self.log("Houdini ERROR (%s): %s" % (prefs, e))
                traceback.print_exc()
        for prefs in c4ds:
            try:
                c4d_fn(prefs, self.log)
                ok += 1
            except Exception as e:
                self.log("C4D ERROR (%s): %s" % (prefs, e))
                traceback.print_exc()
        self.log("Done. Restart the applications for the menus to appear.")
        if ok:
            messagebox.showinfo(
                APP_NAME,
                "%s finished.\n\nRestart Houdini / Cinema 4D to see the "
                "'RS Bridge' menu." % verb)

    def do_install(self):
        self._run(install_houdini, install_c4d, "Install")

    def do_uninstall(self):
        self._run(uninstall_houdini, uninstall_c4d, "Uninstall")


def main_cli():
    print("%s %s -- console install (tkinter unavailable)"
          % (APP_NAME, _tool_version()))
    def log(m):
        print("  " + m)
    for _label, path, preselect in find_houdini_prefs():
        if preselect:
            install_houdini(path, log)
    for _label, path, _pre in find_c4d_prefs():
        install_c4d(path, log)
    print("Done. Restart the applications.")


def main():
    if tk is None:
        main_cli()
        return
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    InstallerUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
