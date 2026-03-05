#!/usr/bin/env python
"""
Probe 3: Django management commands
Tests whether key management commands work (showmigrations, check, inspectdb).
Lists all available commands.
"""
from __future__ import annotations

import os
import sys
import traceback

probe_root = os.path.dirname(os.path.abspath(__file__))
vendor_dir = os.path.join(probe_root, "vendor")
for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testsite.settings")

import django
django.setup()

from io import StringIO

from django.core.management import call_command, get_commands

results = []

print("=== Probe 3: Management Commands ===\n")

# --- Available commands ---
results.append("[Available commands]")
try:
    cmds = sorted(get_commands().keys())
    results.append(f"  Total: {len(cmds)}")
    results.append(f"  Commands: {', '.join(cmds)}")
except Exception:
    results.append(f"  FAILED\n{traceback.format_exc()}")


def run_command(name, *args, **kwargs):
    results.append(f"\n[{name}]")
    try:
        out = StringIO()
        err = StringIO()
        call_command(name, *args, stdout=out, stderr=err, **kwargs)
        stdout_text = out.getvalue().strip()
        stderr_text = err.getvalue().strip()
        results.append(f"  Status: SUCCESS")
        if stdout_text:
            for line in stdout_text.split("\n")[:20]:
                results.append(f"    {line}")
        if stderr_text:
            results.append(f"  stderr: {stderr_text[:300]}")
    except Exception:
        results.append(f"  Status: FAILED\n{traceback.format_exc()}")


# --- Key commands ---
run_command("check")
run_command("showmigrations")
run_command("inspectdb")
run_command("diffsettings")

output = "\n".join(results)
print(output)

results_path = os.path.join(probe_root, "probe3_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 3 ===")
