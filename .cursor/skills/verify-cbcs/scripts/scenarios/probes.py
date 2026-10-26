"""Guest probe sources. Python 3.9. Placeholders __TAR__ and __TREES__ are filled on the Mac."""

MARKER_PATH = "/home/default/verify-cbcs-marker.txt"

MARKER_WRITE = r"""
path = "/home/default/verify-cbcs-marker.txt"
open(path, "w", encoding="utf-8").write("after-checkpoint\n")
root = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
open(__import__("os").path.join(root, "results", "report.txt"), "w").write("MARKER present\n")
print("MARKER present")
"""

MARKER_READ = r"""
import os
path = "/home/default/verify-cbcs-marker.txt"
line = "MARKER present" if os.path.isfile(path) else "MARKER absent"
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

EXTRACT_INSTALLER = r"""
import os, shutil, zipfile
from pathlib import Path
dest = Path("/home/default/choreboy_code_studio_installer_v0.4.13")
if dest.exists():
    shutil.rmtree(dest)
zipfile.ZipFile("/mnt/cbprobe/verify-cbcs/installer.zip").extractall("/home/default", pwd=b"rsd")
root = os.path.dirname(os.path.abspath(__file__))
line = "extracted " + str(dest.is_dir())
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

ASIDE_SCRIPT = r"""
import os
aside = "/home/default/verify-aside"
os.makedirs(aside, exist_ok=True)
install = "/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.14"
dest = os.path.join(aside, "choreboy_code_studio_v0.4.14")
if os.path.exists(install) and not os.path.exists(dest):
    os.rename(install, dest)
    line = "moved " + install
else:
    line = "aside-skip"
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

INSTALL_PRESENT = r"""
import os
path = "/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.13/run_editor.py"
line = ("PRESENT " if os.path.isfile(path) else "MISSING ") + path
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

SNAPSHOT_SCRIPT = r"""
import hashlib, os, tarfile
root = os.path.dirname(os.path.abspath(__file__))
results = os.path.join(root, "results")
os.makedirs(results, exist_ok=True)
tar_path = "__TAR__"
home = "/home/default"
roots = [
    home + "/FreeCAD/CBCS",
    home + "/FreeCAD/Apps",
    home + "/Desktop",
    home + "/.local/share/applications",
    home + "/.local/share/FreeCAD",
    home + "/share",
]
extras = []
try:
    for name in os.listdir(home):
        if name.endswith(".desktop") or "code_studio" in name.lower():
            extras.append(os.path.join(home, name))
except OSError:
    pass
entries = []
parent = os.path.dirname(tar_path)
if parent and not os.path.isdir(parent):
    os.makedirs(parent)

def add_tree(path, entries):
    if not os.path.lexists(path):
        entries.append((path, "missing", 0))
        return
    if os.path.isdir(path) and not os.path.islink(path):
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [n for n in dirnames if n != "lost+found"]
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(full) if not os.path.islink(full) else 0
                except OSError:
                    size = -1
                kind = "link" if os.path.islink(full) else "file"
                entries.append((full, kind, size))
    else:
        kind = "link" if os.path.islink(path) else "file"
        size = 0 if kind == "link" else os.path.getsize(path)
        entries.append((path, kind, size))

with tarfile.open(tar_path, "w:gz") as tar:
    for path in roots + extras:
        if os.path.lexists(path):
            tar.add(path, arcname=path.lstrip("/"))
        add_tree(path, entries)
lines = ["{}\t{}\t{}".format(path, kind, size) for path, kind, size in entries]
lines.sort()
blob = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
digest = hashlib.sha256(blob).hexdigest()
missing_roots = [path for path, kind, size in entries if kind == "missing"]
open(tar_path + ".missing", "w").write("\n".join(missing_roots) + "\n")
text = "SHA256 " + digest + "\ncount " + str(len(entries)) + "\n"
open(os.path.join(results, "report.txt"), "w").write(text)
print(text)
"""

RESTORE_SCRIPT = r"""
import hashlib, os, shutil, tarfile
root = os.path.dirname(os.path.abspath(__file__))
results = os.path.join(root, "results")
os.makedirs(results, exist_ok=True)
tar_path = "__TAR__"
trees = __TREES__
for path in trees:
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
        print("rm", path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
        print("rmtree", path)
    else:
        print("absent", path)
with tarfile.open(tar_path, "r:gz") as tar:
    tar.extractall("/")
print("extracted", os.path.getsize(tar_path))
missing_path = tar_path + ".missing"
if os.path.isfile(missing_path):
    for raw in open(missing_path, encoding="utf-8"):
        path = raw.strip()
        if not path or not os.path.lexists(path):
            continue
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print("rm-missing-root", path)
home = "/home/default"
roots = [
    home + "/FreeCAD/CBCS",
    home + "/FreeCAD/Apps",
    home + "/Desktop",
    home + "/.local/share/applications",
    home + "/.local/share/FreeCAD",
    home + "/share",
]
extras = []
try:
    for name in os.listdir(home):
        if name.endswith(".desktop") or "code_studio" in name.lower():
            extras.append(os.path.join(home, name))
except OSError:
    pass
entries = []

def add_tree(path, entries):
    if not os.path.lexists(path):
        entries.append((path, "missing", 0))
        return
    if os.path.isdir(path) and not os.path.islink(path):
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [n for n in dirnames if n != "lost+found"]
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(full) if not os.path.islink(full) else 0
                except OSError:
                    size = -1
                kind = "link" if os.path.islink(full) else "file"
                entries.append((full, kind, size))
    else:
        kind = "link" if os.path.islink(path) else "file"
        size = 0 if kind == "link" else os.path.getsize(path)
        entries.append((path, kind, size))

for path in roots + extras:
    add_tree(path, entries)
lines = ["{}\t{}\t{}".format(path, kind, size) for path, kind, size in entries]
lines.sort()
blob = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
digest = hashlib.sha256(blob).hexdigest()
cbcs = home + "/FreeCAD/CBCS"
names = sorted(os.listdir(cbcs)) if os.path.isdir(cbcs) else []
text = "SHA256 " + digest + "\nCBCS " + " ".join(names) + "\n"
open(os.path.join(results, "report.txt"), "w").write(text)
print(text)
"""
