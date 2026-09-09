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
import re
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


def _registry_documents():
    """The user's real Documents folder on Windows. Asking the registry is
    the only reliable way: the folder is localized ('Documentos') and is
    often redirected into OneDrive."""
    if sys.platform != "win32":
        return []
    out = []
    try:
        import winreg
        key_path = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                    r"\User Shell Folders")
        for sub in ("User Shell Folders", "Shell Folders"):
            path = key_path.replace("User Shell Folders", sub)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                    value, _t = winreg.QueryValueEx(k, "Personal")
            except OSError:
                continue
            value = os.path.expandvars(value)
            if value and os.path.isdir(value):
                out.append(value)
    except ImportError:
        pass
    return out


def _candidate_doc_dirs():
    """Places Houdini preference folders can live. Covers the home folder,
    the real (possibly localized and OneDrive-redirected) Documents folder,
    and any OneDrive root -- for those the immediate subfolders are scanned
    too, so 'Documentos', 'Dokumente', 'Documenti'... all work without a
    hardcoded list of names."""
    dirs = [_home(), os.path.join(_home(), "Documents")]
    dirs.extend(_registry_documents())

    onedrive_roots = []
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        base = os.environ.get(key)
        if base and os.path.isdir(base):
            onedrive_roots.append(base)
    default_od = os.path.join(_home(), "OneDrive")
    if os.path.isdir(default_od):
        onedrive_roots.append(default_od)
    for base in onedrive_roots:
        dirs.append(base)
        try:
            for name in os.listdir(base):
                sub = os.path.join(base, name)
                if os.path.isdir(sub) and not name.startswith("."):
                    dirs.append(sub)
        except OSError:
            continue

    if sys.platform == "darwin":
        dirs.append(os.path.join(_home(), "Library", "Preferences",
                                 "houdini"))

    seen, out = set(), []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen and os.path.isdir(d):
            seen.add(key)
            out.append(d)
    return out


def _houdini_pref_score(path):
    """Sort key telling apart the preference folder Houdini really uses
    from leftovers. Several can coexist: OneDrive redirection moves
    Documents and leaves an empty decoy behind, and an older location may
    still hold a stale copy. Ranked by (looks like prefs, has content,
    most recently written)."""
    score = 0
    for marker, points in (("houdini.env", 3), ("packages", 3),
                           ("toolbar", 2), ("desktop", 1), ("config", 1)):
        if os.path.exists(os.path.join(path, marker)):
            score += points
    # A live preference folder always holds loose files (houdini.env,
    # *.pref, desktop files...). Abandoned ones keep only empty
    # subdirectories -- sometimes including 'packages' or 'toolbar', which
    # is why the markers above cannot be trusted on their own.
    try:
        has_content = 1 if any(
            os.path.isfile(os.path.join(path, n))
            for n in os.listdir(path)) else 0
    except OSError:
        has_content = 0
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return (has_content, score, mtime)


def _explicit_pref_dirs():
    """Folders named by HOUDINI_USER_PREF_DIR. When a studio (or the user)
    sets it, it overrides every default location, so it wins. The variable
    may contain the __HVER__ token standing for the version."""
    raw = os.environ.get("HOUDINI_USER_PREF_DIR", "").strip()
    if not raw:
        return []
    out = []
    for entry in raw.split(os.pathsep):
        entry = os.path.expandvars(entry.strip())
        if not entry:
            continue
        if "__HVER__" in entry:
            parent = os.path.dirname(entry)
            prefix, _sep, suffix = os.path.basename(entry).partition(
                "__HVER__")
            try:
                names = os.listdir(parent)
            except OSError:
                continue
            for name in names:
                if name.startswith(prefix) and name.endswith(suffix):
                    path = os.path.join(parent, name)
                    if os.path.isdir(path):
                        out.append(path)
        elif os.path.isdir(entry):
            out.append(entry)
    return out


def find_houdini_prefs():
    """Return [(label, path, preselect)] of Houdini preference folders,
    newest version first, with only the most plausible folder of each
    version preselected."""
    found = {}
    explicit = set()
    for path in _explicit_pref_dirs():
        name = os.path.basename(path.rstrip("\\/"))
        ver = name[len("houdini"):] if name.lower().startswith("houdini") \
            else name
        key = os.path.normcase(path)
        found[key] = (ver or name, path)
        explicit.add(key)
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
            # Strictly "20.5" / "21.0.440" -- skips houdini22.0_backup and
            # other lookalike folders users leave around.
            if not re.match(r"^\d+(\.\d+)*$", ver):
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
        # HOUDINI_USER_PREF_DIR overrides every default location, so those
        # folders sort first and are the only ones preselected when set.
        paths = sorted(
            by_version[ver],
            key=lambda p: (os.path.normcase(p) in explicit,
                           _houdini_pref_score(p)),
            reverse=True)
        for i, path in enumerate(paths):
            if explicit:
                preselect = os.path.normcase(path) in explicit
            else:
                # Best candidate of each version, never an empty folder
                # (a leftover rather than a live installation).
                preselect = (i == 0 and _houdini_pref_score(path)[0] == 1)
            out.append(("Houdini %s" % ver, path, preselect))
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
