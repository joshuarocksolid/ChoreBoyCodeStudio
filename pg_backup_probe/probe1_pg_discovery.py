from __future__ import annotations

import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/pg_backup_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

DISCOVERED_PATH = os.path.join(probe_root, "_discovered.json")

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "true")
PG_DATABASE = os.environ.get("PG_DATABASE", "postgres")

results = []


def section(title):
    results.append("")
    results.append(f"[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED")
    results.append(traceback.format_exc().rstrip())


def run_cmd(cmd, timeout=10):
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "error": "",
        }
    except PermissionError:
        return {"returncode": -13, "stdout": "", "stderr": "", "error": "PermissionError"}
    except FileNotFoundError:
        return {"returncode": -1, "stdout": "", "stderr": "", "error": "FileNotFoundError"}
    except subprocess.TimeoutExpired:
        return {"returncode": -2, "stdout": "", "stderr": "", "error": "TimeoutExpired"}
    except Exception as exc:
        return {"returncode": -99, "stdout": "", "stderr": "", "error": str(exc)}


def file_perms(path):
    try:
        st = os.stat(path)
        return {
            "mode": stat.filemode(st.st_mode),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "size": st.st_size,
        }
    except Exception as exc:
        return {"error": str(exc)}


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


def discover_vendor_paths():
    parent = os.path.dirname(probe_root)
    return [
        os.path.join(parent, "ca_invoice_printer", "vendor"),
        "/home/default/ca_invoice_printer/vendor",
        "/home/default/django_probe/vendor",
    ]


def collect_binary_candidates(binary_name):
    paths = []
    resolved = shutil.which(binary_name)
    if resolved:
        paths.append(resolved)
    patterns = [
        f"/usr/lib/postgresql/*/bin/{binary_name}",
        f"/usr/bin/{binary_name}",
        f"/usr/local/bin/{binary_name}",
        f"/opt/freecad/usr/bin/{binary_name}",
    ]
    for pattern in patterns:
        paths.extend(glob.glob(pattern))
    seen = set()
    unique = []
    for path in paths:
        normalized = os.path.normpath(path)
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return sorted(unique)


def probe_binary(binary_name, path):
    info_dict = {
        "path": path,
        "exists": os.path.exists(path),
        "is_file": os.path.isfile(path),
        "readable": os.access(path, os.R_OK),
        "executable": os.access(path, os.X_OK),
        "permissions": file_perms(path),
        "symlink_chain": resolve_symlink_chain(path),
        "version_check": [],
    }
    for args in (["--version"], ["-V"]):
        result = run_cmd([path] + args, timeout=10)
        result["args"] = args
        info_dict["version_check"].append(result)
        if result["returncode"] == 0:
            break
    return info_dict


def write_results_file(filename, content):
    path = os.path.join(results_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 1: PostgreSQL Discovery ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Results dir: {results_dir}")

discovered = {
    "runtime": {
        "python_version": sys.version,
        "executable": sys.executable,
        "probe_root": probe_root,
    },
    "binaries": {},
    "postgres_server": {},
    "connection": {
        "host": PG_HOST,
        "port": PG_PORT,
        "database": PG_DATABASE,
        "user": PG_USER,
    },
}

section("PostgreSQL client binary search")
binary_names = ["pg_dump", "pg_dumpall", "pg_restore", "psql", "postgres", "pg_ctl", "initdb"]
for binary_name in binary_names:
    candidates = collect_binary_candidates(binary_name)
    discovered["binaries"][binary_name] = []
    if not candidates:
        info(f"{binary_name}", "not found")
        continue
    results.append(f"  {binary_name}: {len(candidates)} candidate(s)")
    for path in candidates:
        probed = probe_binary(binary_name, path)
        discovered["binaries"][binary_name].append(probed)
        version_check = probed["version_check"][0] if probed["version_check"] else {}
        code = version_check.get("returncode")
        output = version_check.get("stderr") or version_check.get("stdout") or version_check.get("error", "")
        output = output.splitlines()[0] if output else ""
        results.append(f"    {path}")
        results.append(
            f"      exists={probed['exists']} read={probed['readable']} exec={probed['executable']} code={code}"
        )
        if output:
            results.append(f"      version={output}")

section("pg8000 import")
pg8000 = None
try:
    import pg8000 as pg8000_module

    pg8000 = pg8000_module
    ok("pg8000", getattr(pg8000_module, "__version__", "imported"))
except Exception:
    fail("pg8000")

section("PostgreSQL server facts")
conn = None
if pg8000 is not None:
    try:
        conn = pg8000.connect(
            user=PG_USER,
            host=PG_HOST,
            database=PG_DATABASE,
            port=PG_PORT,
            password=PG_PASSWORD,
            timeout=10,
            application_name="pg_backup_probe_1",
        )
        ok("connect", f"{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")
        cursor = conn.cursor()
        facts = [
            ("server_version", "SHOW server_version"),
            ("data_directory", "SHOW data_directory"),
            ("config_file", "SHOW config_file"),
            ("hba_file", "SHOW hba_file"),
            ("ident_file", "SHOW ident_file"),
        ]
        for key, query in facts:
            try:
                cursor.execute(query)
                row = cursor.fetchone()
                value = row[0] if row else ""
                discovered["postgres_server"][key] = value
                results.append(f"  {key}: {value}")
            except Exception:
                discovered["postgres_server"][key] = ""
                fail(key)
        try:
            cursor.execute(
                "SELECT datname FROM pg_database WHERE datallowconn IS TRUE ORDER BY datname"
            )
            names = [row[0] for row in cursor.fetchall()]
            discovered["postgres_server"]["databases"] = names
            results.append(f"  databases: {', '.join(names)}")
        except Exception:
            fail("database list")
        cursor.close()
    except Exception:
        fail("connect")
    finally:
        if conn is not None:
            try:
                conn.close()
                ok("close connection")
            except Exception:
                fail("close connection")
else:
    info("connect", "skipped because pg8000 import failed")

section("Discovery summary")
for binary_name in ("pg_dump", "pg_dumpall", "psql"):
    entries = discovered["binaries"].get(binary_name, [])
    executable_paths = []
    for entry in entries:
        checks = entry.get("version_check", [])
        if checks and checks[0].get("returncode") == 0:
            executable_paths.append(entry.get("path"))
    if executable_paths:
        ok(binary_name, ", ".join(executable_paths))
    elif entries:
        info(binary_name, "found but execution failed")
    else:
        info(binary_name, "not found")

with open(DISCOVERED_PATH, "w", encoding="utf-8") as handle:
    json.dump(discovered, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Discovery file written]")
results.append(f"  {DISCOVERED_PATH}")

output = "\n".join(results)
print(output)
results_path = write_results_file("probe1_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 1 ===")
