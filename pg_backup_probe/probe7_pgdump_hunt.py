from __future__ import annotations

import configparser
import glob
import json
import os
import stat
import subprocess
import sys
import time
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/pg_backup_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "true")
PG_TARGET_DATABASE = os.environ.get("PG_TARGET_DATABASE", os.environ.get("PG_DATABASE", "postgres"))
PG_SAMPLE_TABLE = os.environ.get("PG_SAMPLE_TABLE", "public.acct_trans")

results = []
pg_dump_candidates = []


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


def write_text_file(filename, content):
    path = os.path.join(results_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def discover_vendor_paths():
    parent = os.path.dirname(probe_root)
    return [
        os.path.join(parent, "ca_invoice_printer", "vendor"),
        "/home/default/ca_invoice_printer/vendor",
        "/home/default/django_probe/vendor",
    ]


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


def file_info(path):
    try:
        st = os.stat(path)
        return {
            "mode": stat.filemode(st.st_mode),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "size": st.st_size,
            "readable": os.access(path, os.R_OK),
            "executable": os.access(path, os.X_OK),
        }
    except Exception as exc:
        return {"error": str(exc)}


def add_candidate(path, source):
    normalized = os.path.normpath(path)
    for existing in pg_dump_candidates:
        if existing["path"] == normalized:
            if source not in existing["sources"]:
                existing["sources"].append(source)
            return
    pg_dump_candidates.append({
        "path": normalized,
        "sources": [source],
        "file_info": file_info(normalized),
        "version_result": None,
        "backup_test_result": None,
    })


def search_proc_for_postgres():
    found_pids = []
    try:
        proc_entries = os.listdir("/proc")
    except Exception as exc:
        info("proc scan", f"cannot read /proc: {exc}")
        return found_pids

    for entry in proc_entries:
        if not entry.isdigit():
            continue
        pid = entry
        comm_path = f"/proc/{pid}/comm"
        try:
            with open(comm_path, "r") as f:
                comm = f.read().strip()
        except Exception:
            continue

        if comm not in ("postgres", "postmaster"):
            continue

        found_pids.append(pid)
        exe_link = f"/proc/{pid}/exe"
        try:
            real_exe = os.readlink(exe_link)
            info(f"  pid {pid}", f"comm={comm} exe={real_exe}")
            bin_dir = os.path.dirname(real_exe)
            pg_dump_path = os.path.join(bin_dir, "pg_dump")
            if os.path.isfile(pg_dump_path):
                add_candidate(pg_dump_path, f"/proc/{pid}/exe sibling")
            pg_dump_all_path = os.path.join(bin_dir, "pg_dumpall")
            if os.path.isfile(pg_dump_all_path):
                info(f"  pg_dumpall also found", pg_dump_all_path)
        except PermissionError:
            info(f"  pid {pid}", f"comm={comm} exe=PermissionError (cannot readlink)")
            cmdline_path = f"/proc/{pid}/cmdline"
            try:
                with open(cmdline_path, "rb") as f:
                    cmdline_raw = f.read()
                cmdline_parts = cmdline_raw.split(b"\x00")
                argv0 = cmdline_parts[0].decode("utf-8", errors="replace") if cmdline_parts else ""
                if argv0 and os.path.isabs(argv0):
                    info(f"  pid {pid} cmdline[0]", argv0)
                    bin_dir = os.path.dirname(argv0)
                    pg_dump_path = os.path.join(bin_dir, "pg_dump")
                    if os.path.isfile(pg_dump_path):
                        add_candidate(pg_dump_path, f"/proc/{pid}/cmdline sibling")
            except Exception:
                pass
        except Exception as exc:
            info(f"  pid {pid}", f"comm={comm} exe error: {exc}")

    return found_pids


def search_pgadmin3_config():
    config_locations = [
        os.path.expanduser("~/.pgadmin3"),
        "/home/default/.pgadmin3",
        os.path.expanduser("~/pgadmin3.conf"),
        "/home/default/pgadmin3.conf",
        os.path.expanduser("~/.config/pgadmin3"),
    ]
    seen_dirs = set()
    for base in config_locations:
        if base in seen_dirs:
            continue
        seen_dirs.add(base)

        if os.path.isdir(base):
            info(f"  config dir exists", base)
            try:
                for item in os.listdir(base):
                    info(f"    entry", item)
                    full = os.path.join(base, item)
                    if os.path.isfile(full):
                        parse_pgadmin_file(full)
            except Exception as exc:
                info(f"  config dir scan error", str(exc))
        elif os.path.isfile(base):
            info(f"  config file exists", base)
            parse_pgadmin_file(base)
        else:
            info(f"  config path not found", base)


def parse_pgadmin_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        info(f"  read error", f"{filepath}: {exc}")
        return

    for line in content.splitlines():
        line_lower = line.lower()
        if any(kw in line_lower for kw in ("binpath", "pgbin", "bin_path", "pg_dump", "dumppath")):
            info(f"  interesting line", f"{filepath}: {line.strip()}")

        if "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value and os.path.isabs(value) and ("bin" in key.lower() or "dump" in key.lower()):
                pg_dump_test = os.path.join(value, "pg_dump") if os.path.isdir(value) else value
                if os.path.isfile(pg_dump_test):
                    add_candidate(pg_dump_test, f"pgadmin3 config ({filepath})")

    cp = configparser.ConfigParser(strict=False)
    try:
        cp.read_string(content)
        for sec in cp.sections():
            for key, value in cp.items(sec):
                if value and os.path.isabs(value) and ("bin" in key or "dump" in key or "path" in key):
                    pg_dump_test = os.path.join(value, "pg_dump") if os.path.isdir(value) else value
                    if os.path.isfile(pg_dump_test):
                        add_candidate(pg_dump_test, f"pgadmin3 ini [{sec}].{key}")
    except Exception:
        pass


def search_filesystem_broadly():
    search_roots = ["/usr", "/opt", "/home"]
    extra_checks = [
        "/home/PG_data/../bin/pg_dump",
        "/home/PG_bin/pg_dump",
        "/home/postgres/bin/pg_dump",
    ]

    for extra in extra_checks:
        normalized = os.path.normpath(extra)
        if os.path.isfile(normalized):
            add_candidate(normalized, f"known-location ({normalized})")
            info(f"  found at known location", normalized)

    globs = [
        "/usr/lib/postgresql/*/bin/pg_dump",
        "/usr/local/pgsql/bin/pg_dump",
        "/opt/postgresql/*/bin/pg_dump",
        "/opt/pgsql/bin/pg_dump",
    ]
    for pattern in globs:
        hits = glob.glob(pattern)
        for hit in hits:
            add_candidate(hit, f"glob ({pattern})")
            info(f"  found via glob", hit)

    for search_root in search_roots:
        if not os.path.isdir(search_root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(search_root, followlinks=False):
                depth = dirpath.count(os.sep) - search_root.count(os.sep)
                if depth > 5:
                    dirnames.clear()
                    continue

                skip_dirs = {"__pycache__", ".git", "node_modules", "venv", ".venv"}
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]

                if "pg_dump" in filenames:
                    full_path = os.path.join(dirpath, "pg_dump")
                    add_candidate(full_path, f"walk ({search_root})")
                    info(f"  found via walk", full_path)
        except PermissionError:
            info(f"  walk permission denied", search_root)
        except Exception as exc:
            info(f"  walk error", f"{search_root}: {exc}")


def test_pg_dump_execution(candidate):
    path = candidate["path"]
    version_result = run_cmd([path, "--version"], timeout=10)
    candidate["version_result"] = version_result

    version_output = version_result.get("stdout") or version_result.get("stderr") or ""
    version_line = version_output.splitlines()[0] if version_output else ""

    if version_result["returncode"] == 0:
        ok(f"  version check", f"path={path} output={version_line}")
        return True
    elif version_result["error"] == "PermissionError":
        info(f"  version check BLOCKED", f"path={path} PermissionError (AppArmor?)")
        return False
    elif version_result["error"] == "FileNotFoundError":
        info(f"  version check MISSING", f"path={path} FileNotFoundError")
        return False
    else:
        info(f"  version check FAILED",
             f"path={path} code={version_result['returncode']} error={version_result['error'] or version_line}")
        return False


def test_pg_dump_backup(candidate):
    path = candidate["path"]

    parts = PG_SAMPLE_TABLE.split(".", 1)
    if len(parts) == 2:
        table_arg = f"{parts[0]}.{parts[1]}"
    else:
        table_arg = PG_SAMPLE_TABLE

    cmd = [
        path,
        "-h", PG_HOST,
        "-p", str(PG_PORT),
        "-U", PG_USER,
        "-t", table_arg,
        "--no-password",
        PG_TARGET_DATABASE,
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASSWORD

    start = time.time()
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        elapsed = time.time() - start
        backup_result = {
            "returncode": completed.returncode,
            "stdout_bytes": len(completed.stdout.encode("utf-8")),
            "stdout_preview": completed.stdout[:500] if completed.stdout else "",
            "stderr_preview": completed.stderr[:500] if completed.stderr else "",
            "elapsed_seconds": elapsed,
            "error": "",
        }
    except PermissionError:
        backup_result = {
            "returncode": -13,
            "stdout_bytes": 0,
            "stdout_preview": "",
            "stderr_preview": "",
            "elapsed_seconds": time.time() - start,
            "error": "PermissionError",
        }
    except subprocess.TimeoutExpired:
        backup_result = {
            "returncode": -2,
            "stdout_bytes": 0,
            "stdout_preview": "",
            "stderr_preview": "",
            "elapsed_seconds": time.time() - start,
            "error": "TimeoutExpired",
        }
    except Exception as exc:
        backup_result = {
            "returncode": -99,
            "stdout_bytes": 0,
            "stdout_preview": "",
            "stderr_preview": "",
            "elapsed_seconds": time.time() - start,
            "error": str(exc),
        }

    candidate["backup_test_result"] = backup_result

    if backup_result["returncode"] == 0 and backup_result["stdout_bytes"] > 0:
        ok(f"  backup test",
           f"table={table_arg} db={PG_TARGET_DATABASE} bytes={backup_result['stdout_bytes']} "
           f"elapsed={backup_result['elapsed_seconds']:.3f}s")
        return True
    else:
        detail = backup_result["error"] or backup_result["stderr_preview"][:200] or f"code={backup_result['returncode']}"
        info(f"  backup test FAILED", detail)
        return False


for vendor_path in discover_vendor_paths():
    if vendor_path not in sys.path and os.path.isdir(vendor_path):
        sys.path.insert(0, vendor_path)

print("=== Probe 7: pg_dump Hunt ===")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Target database: {PG_TARGET_DATABASE}")
results.append(f"  Sample table: {PG_SAMPLE_TABLE}")

section("Strategy 1: Find postgres via /proc")
found_pids = search_proc_for_postgres()
if not found_pids:
    info("proc scan", "no postgres/postmaster processes found in /proc")
else:
    info("proc scan", f"found {len(found_pids)} postgres process(es)")

section("Strategy 2: pgAdmin3 configuration")
search_pgadmin3_config()

section("Strategy 3: Broad filesystem search")
search_filesystem_broadly()

section("Candidate summary")
if not pg_dump_candidates:
    info("candidates", "NONE FOUND across all search strategies")
else:
    info("candidates", f"{len(pg_dump_candidates)} unique path(s) found")
    for i, candidate in enumerate(pg_dump_candidates):
        fi = candidate["file_info"]
        info(f"  [{i+1}] {candidate['path']}",
             f"sources={candidate['sources']} "
             f"readable={fi.get('readable', '?')} "
             f"executable={fi.get('executable', '?')} "
             f"mode={fi.get('mode', '?')} "
             f"size={fi.get('size', '?')}")

section("Execution tests")
any_executable = False
executable_path = None
if not pg_dump_candidates:
    info("execution", "no candidates to test")
else:
    for candidate in pg_dump_candidates:
        success = test_pg_dump_execution(candidate)
        if success:
            any_executable = True
            executable_path = candidate["path"]

section("Backup tests")
backup_ok = False
if executable_path:
    for candidate in pg_dump_candidates:
        if candidate["path"] == executable_path:
            backup_ok = test_pg_dump_backup(candidate)
            break
else:
    info("backup test", "skipped (no executable pg_dump found)")

section("Recommendation")
recommendation = "use_pg8000"
version_string = ""
found = len(pg_dump_candidates) > 0

if executable_path:
    ver = None
    for candidate in pg_dump_candidates:
        if candidate["path"] == executable_path and candidate.get("version_result"):
            ver = candidate["version_result"]
            break
    if ver:
        version_string = (ver.get("stdout") or ver.get("stderr") or "").splitlines()[0] if ver else ""

if executable_path and backup_ok:
    recommendation = "use_pgdump"
    info("recommendation", "USE pg_dump (subprocess)")
    info("rationale", f"pg_dump found at {executable_path}, executable, and backup test passed")
elif executable_path and not backup_ok:
    recommendation = "use_pgdump_with_caveats"
    info("recommendation", "USE pg_dump (subprocess) with adjusted parameters")
    info("rationale", f"pg_dump at {executable_path} runs but backup test failed; "
         "may need different database/table target")
elif found and not any_executable:
    recommendation = "needs_bridge"
    info("recommendation", "NEEDS bridge script or fallback to pg8000")
    info("rationale", "pg_dump found on filesystem but cannot be executed from AppRun (likely AppArmor)")
else:
    recommendation = "use_pg8000"
    info("recommendation", "USE pure-Python pg8000 backup")
    info("rationale", "pg_dump not found anywhere on the system; pg8000 path is fully validated by probes 3-5")

status = {
    "found": found,
    "path": executable_path or (pg_dump_candidates[0]["path"] if pg_dump_candidates else None),
    "executable_from_apprun": any_executable,
    "version": version_string,
    "backup_test_passed": backup_ok,
    "recommendation": recommendation,
    "candidate_count": len(pg_dump_candidates),
    "candidates": [],
    "search_strategies": {
        "proc_pids_found": len(found_pids),
        "pgadmin_config_searched": True,
        "filesystem_walk_searched": True,
    },
}

for candidate in pg_dump_candidates:
    c = {
        "path": candidate["path"],
        "sources": candidate["sources"],
        "file_info": candidate["file_info"],
    }
    if candidate.get("version_result"):
        vr = candidate["version_result"]
        c["version_check"] = {
            "returncode": vr["returncode"],
            "stdout": vr["stdout"][:300],
            "stderr": vr["stderr"][:300],
            "error": vr["error"],
        }
    if candidate.get("backup_test_result"):
        br = candidate["backup_test_result"]
        c["backup_test"] = {
            "returncode": br["returncode"],
            "stdout_bytes": br["stdout_bytes"],
            "elapsed_seconds": br["elapsed_seconds"],
            "error": br["error"],
            "stderr_preview": br["stderr_preview"][:300],
        }
    status["candidates"].append(c)

status_path = os.path.join(results_dir, "probe7_pgdump_status.json")
with open(status_path, "w", encoding="utf-8") as handle:
    json.dump(status, handle, indent=2, sort_keys=True)

results.append("")
results.append("[Status JSON written]")
results.append(f"  {status_path}")

output = "\n".join(results)
print(output)
results_path = write_text_file("probe7_results.txt", output)
print("")
print(f"Results written to {results_path}")
print("=== END Probe 7 ===")
