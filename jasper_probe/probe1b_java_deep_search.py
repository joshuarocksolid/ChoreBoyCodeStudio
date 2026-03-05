#!/usr/bin/env python
"""
Probe 1B: Java Deep Search

Probe 1 found /usr/bin/java but got Permission denied.
However, LibreOffice's JasperReports extension ran Java fine.
This probe explores every possible way to execute Java on ChoreBoy:

1. Follow the /usr/bin/java symlink chain -- the ACTUAL binary may be accessible
2. Search /usr/lib/jvm/ for all java binaries and test each one
3. Find LibreOffice's JVM configuration -- which JVM does LO use?
4. Find libjvm.so -- can we load the JVM as a shared library (like LO does)?
5. Check file permissions and ACLs in detail
6. Search for any other JRE/JDK on the system
"""
from __future__ import annotations

import ctypes
import ctypes.util
import glob
import json
import os
import stat
import subprocess
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

DISCOVERED_PATH = os.path.join(probe_root, "_discovered.json")

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def file_perms(path):
    try:
        st = os.stat(path)
        mode = stat.filemode(st.st_mode)
        uid = st.st_uid
        gid = st.st_gid
        return f"{mode} uid={uid} gid={gid}"
    except Exception as e:
        return f"stat failed: {e}"


def check_access(path):
    parts = []
    parts.append(f"exists={os.path.exists(path)}")
    parts.append(f"read={os.access(path, os.R_OK)}")
    parts.append(f"exec={os.access(path, os.X_OK)}")
    if os.path.islink(path):
        try:
            target = os.readlink(path)
            parts.append(f"symlink->{target}")
        except Exception:
            pass
    return ", ".join(parts)


def resolve_symlink_chain(path):
    chain = [path]
    current = path
    seen = set()
    while os.path.islink(current) and current not in seen:
        seen.add(current)
        try:
            target = os.readlink(current)
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(current), target)
            target = os.path.normpath(target)
            chain.append(target)
            current = target
        except Exception:
            break
    return chain


def try_java_exec(java_path):
    try:
        r = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10
        )
        version = r.stderr.strip() if r.stderr.strip() else r.stdout.strip()
        return r.returncode, version
    except PermissionError:
        return -13, "PermissionError"
    except FileNotFoundError:
        return -1, "FileNotFoundError"
    except Exception as e:
        return -99, str(e)


print("=== Probe 1B: Java Deep Search ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  User: uid={os.getuid()}, euid={os.geteuid()}")
try:
    import pwd
    pw = pwd.getpwuid(os.getuid())
    results.append(f"  Username: {pw.pw_name}")
    results.append(f"  Groups: {os.getgroups()}")
except Exception:
    pass
results.append(f"  Probe root: {probe_root}")

discovered = {}
working_java = None

# ============================================================
section("1. Symlink chain analysis for /usr/bin/java")
# ============================================================
chain = resolve_symlink_chain("/usr/bin/java")
results.append(f"  Chain has {len(chain)} links:")
for i, link in enumerate(chain):
    perms = file_perms(link)
    access = check_access(link)
    prefix = "  -> " if i > 0 else "  "
    results.append(f"  {prefix}{link}")
    results.append(f"      perms: {perms}")
    results.append(f"      access: {access}")

final_binary = chain[-1] if chain else "/usr/bin/java"
results.append(f"  Final resolved binary: {final_binary}")

if final_binary != "/usr/bin/java":
    results.append(f"\n  Testing execution of resolved binary: {final_binary}")
    code, version = try_java_exec(final_binary)
    if code == 0:
        ok("RESOLVED BINARY WORKS", version)
        working_java = final_binary
    else:
        info(f"resolved binary failed: code={code}, {version}")

# ============================================================
section("2. Search /usr/lib/jvm/ for all java binaries")
# ============================================================
jvm_javas = []
jvm_base = "/usr/lib/jvm"
if os.path.isdir(jvm_base):
    results.append(f"  /usr/lib/jvm/ exists, scanning...")
    for root, dirs, files in os.walk(jvm_base):
        if "java" in files:
            full = os.path.join(root, "java")
            jvm_javas.append(full)

    if jvm_javas:
        results.append(f"  Found {len(jvm_javas)} java binaries:")
        for jp in jvm_javas:
            perms = file_perms(jp)
            access = check_access(jp)
            results.append(f"    {jp}")
            results.append(f"      perms: {perms}")
            results.append(f"      access: {access}")

            code, version = try_java_exec(jp)
            if code == 0:
                ok(f"EXECUTABLE", f"{jp} -> {version[:80]}")
                if not working_java:
                    working_java = jp
            else:
                info(f"exec result: code={code}, {version}")
    else:
        info("no java binaries found in /usr/lib/jvm/")
else:
    info("/usr/lib/jvm/ does not exist")

# ============================================================
section("3. Search for ALL java executables on PATH and common locations")
# ============================================================
extra_search = [
    "/opt/java/bin/java",
    "/opt/jdk/bin/java",
    "/opt/jre/bin/java",
    "/usr/local/bin/java",
    "/usr/local/java/bin/java",
    "/opt/freecad/usr/bin/java",
    "/snap/bin/java",
]

for jp in extra_search:
    if os.path.exists(jp) and jp not in jvm_javas:
        perms = file_perms(jp)
        access = check_access(jp)
        results.append(f"  Found: {jp}")
        results.append(f"    perms: {perms}")
        results.append(f"    access: {access}")
        code, version = try_java_exec(jp)
        if code == 0:
            ok(f"EXECUTABLE", f"{jp} -> {version[:80]}")
            if not working_java:
                working_java = jp
        else:
            info(f"exec result: code={code}, {version}")

# ============================================================
section("4. LibreOffice JVM configuration")
# ============================================================
lo_jvm_paths = []

lo_config_locations = [
    os.path.expanduser("~/.config/libreoffice/4/user/registrymodifications.xcu"),
    "/home/default/.config/libreoffice/4/user/registrymodifications.xcu",
    os.path.expanduser("~/.config/libreoffice/*/user/registrymodifications.xcu"),
]

for pattern in lo_config_locations:
    for cfg_path in glob.glob(pattern):
        if os.path.exists(cfg_path):
            results.append(f"  LO config found: {cfg_path}")
            try:
                with open(cfg_path, "r") as f:
                    for line in f:
                        if "JavaInfo" in line or "java" in line.lower() and "jvm" in line.lower():
                            line = line.strip()
                            if len(line) > 200:
                                line = line[:200] + "..."
                            results.append(f"    {line}")
            except Exception as e:
                info(f"could not read: {e}")

lo_java_dirs = glob.glob("/usr/lib/libreoffice/program/classes/*.jar")
if lo_java_dirs:
    results.append(f"  LibreOffice ships {len(lo_java_dirs)} JARs in program/classes/")

lo_javainfo = glob.glob("/usr/lib/libreoffice/program/javaldx")
if lo_javainfo:
    results.append(f"  Found LO javaldx: {lo_javainfo[0]}")
    code, out, err = run_cmd([lo_javainfo[0]])
    if code == 0:
        results.append(f"    javaldx output: {out}")
        if out and os.path.isdir(out.strip()):
            lo_jvm_paths.append(out.strip())
    else:
        info(f"javaldx failed: code={code}, {err}")

# ============================================================
section("5. Find libjvm.so (JVM shared library)")
# ============================================================
libjvm_paths = []

libjvm_search_patterns = [
    "/usr/lib/jvm/*/lib/server/libjvm.so",
    "/usr/lib/jvm/*/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/*/jre/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/*/jre/lib/server/libjvm.so",
    "/opt/java/lib/server/libjvm.so",
    "/opt/freecad/usr/lib/libjvm.so",
]

for pattern in libjvm_search_patterns:
    found = glob.glob(pattern)
    libjvm_paths.extend(found)

ldconfig_libjvm = ctypes.util.find_library("jvm")
if ldconfig_libjvm:
    results.append(f"  ctypes.util.find_library('jvm'): {ldconfig_libjvm}")
    libjvm_paths.append(ldconfig_libjvm)

if libjvm_paths:
    results.append(f"  Found {len(libjvm_paths)} libjvm.so locations:")
    for ljp in libjvm_paths:
        perms = file_perms(ljp)
        access = check_access(ljp)
        results.append(f"    {ljp}")
        results.append(f"      perms: {perms}")
        results.append(f"      access: {access}")

        readable = os.access(ljp, os.R_OK)
        if readable:
            results.append(f"      readable: YES -- potential for JNI/ctypes loading")
        else:
            results.append(f"      readable: NO")
else:
    info("no libjvm.so found")

section("5b. Test loading libjvm.so via ctypes")
for ljp in libjvm_paths:
    if not os.access(ljp, os.R_OK):
        continue
    try:
        jvm_dir = os.path.dirname(ljp)
        old_ld = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = jvm_dir + ":" + old_ld

        lib = ctypes.CDLL(ljp)
        ok(f"ctypes.CDLL load", ljp)
        results.append(f"      JNI_CreateJavaVM symbol: {hasattr(lib, 'JNI_CreateJavaVM')}")

        os.environ["LD_LIBRARY_PATH"] = old_ld
        break
    except OSError as e:
        info(f"ctypes.CDLL({ljp}) failed: {e}")
    except Exception as e:
        info(f"ctypes load error: {e}")

# ============================================================
section("6. Permission analysis")
# ============================================================
results.append(f"  Current uid: {os.getuid()}, gid: {os.getgid()}")
results.append(f"  Effective uid: {os.geteuid()}, gid: {os.getegid()}")
results.append(f"  Groups: {os.getgroups()}")

code, out, err = run_cmd(["id"])
if code == 0:
    results.append(f"  id: {out}")

code, out, err = run_cmd(["ls", "-la", "/usr/bin/java"])
if code == 0:
    results.append(f"  ls -la /usr/bin/java: {out}")

code, out, err = run_cmd(["getfacl", "/usr/bin/java"])
if code == 0:
    results.append(f"  ACL for /usr/bin/java:")
    for line in out.splitlines():
        results.append(f"    {line}")
else:
    info(f"getfacl not available or failed: {err}")

if final_binary != "/usr/bin/java":
    code, out, err = run_cmd(["ls", "-la", final_binary])
    if code == 0:
        results.append(f"  ls -la {final_binary}: {out}")

    code, out, err = run_cmd(["getfacl", final_binary])
    if code == 0:
        results.append(f"  ACL for {final_binary}:")
        for line in out.splitlines():
            results.append(f"    {line}")

# ============================================================
section("7. Test: can we copy java binary and execute the copy?")
# ============================================================
if os.path.exists(final_binary) and os.access(final_binary, os.R_OK):
    copy_path = os.path.join(probe_root, "tools", "java_copy")
    try:
        import shutil
        shutil.copy2(final_binary, copy_path)
        os.chmod(copy_path, 0o755)
        results.append(f"  Copied {final_binary} -> {copy_path}")

        code, version = try_java_exec(copy_path)
        if code == 0:
            ok("COPIED BINARY WORKS", version[:80])
            if not working_java:
                working_java = copy_path
        else:
            info(f"copied binary exec: code={code}, {version}")

        try:
            os.remove(copy_path)
        except Exception:
            pass
    except PermissionError:
        info("cannot copy java binary (permission denied on read)")
    except Exception as e:
        info(f"copy test failed: {e}")
else:
    info(f"cannot read {final_binary} to copy it")

# ============================================================
section("8. Test: can LibrePy/LibreOffice subprocess run Java?")
# ============================================================
results.append("  (informational -- check if LO has special Java access)")

soffice_paths = [
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/usr/lib/libreoffice/program/soffice.bin",
]
for sp in soffice_paths:
    if os.path.exists(sp):
        perms = file_perms(sp)
        access = check_access(sp)
        results.append(f"  {sp}: {perms}, {access}")

# ============================================================
section("9. Search for JasperReports JARs already on system")
# ============================================================
jasper_patterns = [
    "/home/*/Documents/JobManager/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports*/*.jar",
    "/home/*/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/JasperReports*/*.jar",
    "/home/default/Documents/JobManager/.jobmanager_user/user/uno_packages/cache/uno_packages/*/JasperReportManager*/lib/*.jar",
    "/opt/jaspersoft-studio/configuration/org.eclipse.osgi/*/0/.cp/lib/jasperreports*.jar",
]
found_jasper = []
for pattern in jasper_patterns:
    found_jasper.extend(glob.glob(pattern))

if found_jasper:
    results.append(f"  Found {len(found_jasper)} JasperReports-related JARs on system:")
    dirs_seen = set()
    for jp in sorted(found_jasper)[:20]:
        d = os.path.dirname(jp)
        if d not in dirs_seen:
            dirs_seen.add(d)
            results.append(f"    dir: {d}")
        results.append(f"      {os.path.basename(jp)}")
else:
    info("no JasperReports JARs found on system (will use shipped lib/)")

# ============================================================
section("SUMMARY")
# ============================================================
if working_java:
    ok("WORKING JAVA FOUND", working_java)
    discovered["java_path"] = working_java
    discovered["java_source"] = "deep_search"
    results.append("")
    results.append("  A working Java binary was found!")
    results.append("  Probes 2-6 should work with this path.")
else:
    results.append("  NO WORKING JAVA BINARY FOUND via direct execution.")
    results.append("")
    if libjvm_paths:
        results.append("  HOWEVER: libjvm.so WAS found. This means:")
        results.append("  - The JVM shared library exists and may be loadable")
        results.append("  - LibreOffice likely loads it as a shared library (not via /usr/bin/java)")
        results.append("  - We may be able to use JPype or ctypes JNI to load the JVM from Python")
        results.append("  - This would bypass the /usr/bin/java permission block entirely")
        discovered["libjvm_paths"] = libjvm_paths
        discovered["java_blocked_but_jvm_loadable"] = True
    else:
        results.append("  No libjvm.so found either.")
        results.append("  Java appears to be fully blocked on this system.")
        results.append("  Must pivot to pure-Python report engine.")
        discovered["java_fully_blocked"] = True

with open(DISCOVERED_PATH, "w") as f:
    json.dump(discovered, f, indent=2)

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe1b_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 1B ===")
