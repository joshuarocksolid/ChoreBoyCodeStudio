#!/usr/bin/env python
"""
Probe 10: DRF API serving and HTTP consumption
Tests whether Django REST Framework can serve a JSON API via runserver
and whether another process can consume it over localhost HTTP.
This is the key question from PROBE_ANALYSIS.md Open Question 2.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

probe_root = os.path.dirname(os.path.abspath(__file__))
vendor_dir = os.path.join(probe_root, "vendor")
for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

HOST = "127.0.0.1"
PORT = 8321
BASE_URL = f"http://{HOST}:{PORT}"
API_URL = f"{BASE_URL}/api/tasks/"
STARTUP_TIMEOUT = 15

results = []
server_proc = None


def check(label, fn):
    try:
        val = fn()
        results.append(f"  {label}: YES ({val})")
        return val
    except Exception:
        results.append(f"  {label}: FAILED\n{traceback.format_exc()}")
        return None


def api_request(method, url, data=None):
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        resp_body = resp.read().decode("utf-8")
        return resp.status, json.loads(resp_body) if resp_body.strip() else None
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8") if e.fp else ""
        return e.code, resp_body


def wait_for_server():
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            s = socket.create_connection((HOST, PORT), timeout=1)
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def kill_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        try:
            os.kill(server_proc.pid, signal.SIGTERM)
            server_proc.wait(timeout=5)
        except Exception:
            try:
                server_proc.kill()
                server_proc.wait(timeout=3)
            except Exception:
                pass


print("=== Probe 10: DRF API Serving & HTTP Consumption ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version.split()[0]}")
results.append(f"  Probe root: {probe_root}")
results.append(f"  Target: {BASE_URL}")

apprun = "/opt/freecad/AppRun"
use_apprun = os.path.isfile(apprun) and os.access(apprun, os.X_OK)
server_exe = apprun if use_apprun else sys.executable

results.append("\n[Pre-flight: run migrations]")
os.environ["DJANGO_SETTINGS_MODULE"] = "testsite.settings_drf"
settings_contaminated = False
try:
    import django
    already_setup = django.apps.apps.ready
    if already_setup:
        from django.conf import settings as _settings
        active_module = _settings.SETTINGS_MODULE
        if active_module != "testsite.settings_drf":
            settings_contaminated = True
            results.append(f"  WARNING: Django already initialized with '{active_module}'")
            results.append(f"  Skipping in-process migrate (subprocess gets fresh settings).")
        else:
            django.setup()
    else:
        django.setup()

    if not settings_contaminated:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("migrate", verbosity=0, stdout=out)
        results.append("  migrate: SUCCESS")
    else:
        migrate_code = (
            "import sys,os;"
            f"root='{probe_root}';"
            "sys.path.insert(0,os.path.join(root,'vendor'));"
            "sys.path.insert(0,root);"
            "os.chdir(root);"
            "os.environ['DJANGO_SETTINGS_MODULE']='testsite.settings_drf';"
            "import django;django.setup();"
            "from django.core.management import call_command;"
            "call_command('migrate',verbosity=1)"
        )
        migrate_cmd = [server_exe, "-c", migrate_code]
        migrate_result = subprocess.run(
            migrate_cmd,
            cwd=probe_root,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "testsite.settings_drf"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        if migrate_result.returncode == 0:
            results.append("  migrate (subprocess): SUCCESS")
        else:
            results.append(f"  migrate (subprocess): FAILED (exit code {migrate_result.returncode})")
            if migrate_result.stderr:
                results.append(f"  stderr: {migrate_result.stderr[:1000]}")
except Exception:
    results.append(f"  migrate: FAILED\n{traceback.format_exc()}")

server_code = (
    "import sys,os;"
    f"root='{probe_root}';"
    "sys.path.insert(0,os.path.join(root,'vendor'));"
    "sys.path.insert(0,root);"
    "os.chdir(root);"
    "os.environ['DJANGO_SETTINGS_MODULE']='testsite.settings_drf';"
    f"sys.argv=['manage.py','runserver','{HOST}:{PORT}','--noreload'];"
    "from django.core.management import execute_from_command_line;"
    "execute_from_command_line(sys.argv)"
)

results.append("\n[Start runserver subprocess]")
results.append(f"  Executable: {server_exe}")
results.append(f"  Launch mode: -c inline code")
try:
    server_proc = subprocess.Popen(
        [server_exe, "-c", server_code],
        cwd=probe_root,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "testsite.settings_drf",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    results.append(f"  PID: {server_proc.pid}")

    if wait_for_server():
        results.append(f"  Server accepting connections on {HOST}:{PORT}: YES")
    else:
        stderr_out = ""
        exit_code = server_proc.poll()
        if exit_code is not None:
            try:
                _, err = server_proc.communicate(timeout=3)
                stderr_out = err.decode("utf-8", errors="replace") if err else ""
            except Exception:
                pass
        results.append(f"  Server accepting connections: FAILED (timeout {STARTUP_TIMEOUT}s)")
        results.append(f"  Server exit code: {exit_code}")
        if stderr_out:
            results.append(f"  Server stderr:\n{stderr_out[:2000]}")
        kill_server()
        output = "\n".join(results)
        print(output)
        results_dir = os.path.join(probe_root, "results")
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "probe10_results.txt"), "w") as f:
            f.write(output)
        print(f"\nResults written to results/probe10_results.txt")
        print("\n=== END Probe 10 (server failed to start) ===")
        sys.exit(1)
except Exception:
    results.append(f"  Start server: FAILED\n{traceback.format_exc()}")
    kill_server()
    output = "\n".join(results)
    print(output)
    sys.exit(1)

try:
    results.append("\n[API: GET /api/tasks/ (initial list)]")
    status, body = api_request("GET", API_URL)
    results.append(f"  Status: {status}")
    results.append(f"  Body type: {type(body).__name__}")
    initial_count = len(body) if isinstance(body, list) else "N/A"
    results.append(f"  Item count: {initial_count}")

    results.append("\n[API: POST /api/tasks/ (create)]")
    status, body = api_request("POST", API_URL, {"title": "Probe 10 task", "done": False})
    results.append(f"  Status: {status}")
    created_id = None
    if isinstance(body, dict):
        created_id = body.get("id")
        results.append(f"  Created: id={created_id}, title='{body.get('title')}'")
    else:
        results.append(f"  Response: {body}")

    if created_id:
        detail_url = f"{API_URL}{created_id}/"

        results.append("\n[API: GET /api/tasks/{id}/ (retrieve)]")
        status, body = api_request("GET", detail_url)
        results.append(f"  Status: {status}")
        if isinstance(body, dict):
            results.append(f"  Retrieved: id={body.get('id')}, title='{body.get('title')}', done={body.get('done')}")
        else:
            results.append(f"  Response: {body}")

        results.append("\n[API: PATCH /api/tasks/{id}/ (partial update)]")
        status, body = api_request("PATCH", detail_url, {"done": True})
        results.append(f"  Status: {status}")
        if isinstance(body, dict):
            results.append(f"  Updated: done={body.get('done')}")
        else:
            results.append(f"  Response: {body}")

        results.append("\n[API: PUT /api/tasks/{id}/ (full update)]")
        status, body = api_request("PUT", detail_url, {"title": "Probe 10 updated", "done": False})
        results.append(f"  Status: {status}")
        if isinstance(body, dict):
            results.append(f"  Updated: title='{body.get('title')}', done={body.get('done')}")
        else:
            results.append(f"  Response: {body}")

        results.append("\n[API: DELETE /api/tasks/{id}/ (destroy)]")
        status, body = api_request("DELETE", detail_url)
        results.append(f"  Status: {status}")
        results.append(f"  Body: {body}")

        results.append("\n[API: GET /api/tasks/ (confirm deletion)]")
        status, body = api_request("GET", API_URL)
        results.append(f"  Status: {status}")
        final_count = len(body) if isinstance(body, list) else "N/A"
        results.append(f"  Item count after delete: {final_count}")
    else:
        results.append("\n  [Skipping retrieve/update/delete: no created_id]")

except Exception:
    results.append(f"\n[API test error]\n{traceback.format_exc()}")

finally:
    results.append("\n[Shutdown]")
    kill_server()
    if server_proc:
        results.append(f"  Server process terminated (exit code: {server_proc.returncode})")
    else:
        results.append("  No server process to terminate")

output = "\n".join(results)
print(output)

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)
results_path = os.path.join(results_dir, "probe10_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 10 ===")
