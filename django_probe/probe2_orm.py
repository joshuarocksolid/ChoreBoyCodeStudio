#!/usr/bin/env python
"""
Probe 2: Django ORM - migrations and CRUD
Tests whether Django can run migrations against SQLite and perform
create / read / update / delete operations.
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

from django.core.management import call_command

results = []

print("=== Probe 2: Django ORM ===\n")

# --- Migrate ---
results.append("[Migrate]")
try:
    out = StringIO()
    call_command("migrate", verbosity=1, stdout=out)
    migrate_output = out.getvalue()
    results.append(f"  migrate: SUCCESS")
    for line in migrate_output.strip().split("\n")[-5:]:
        results.append(f"    {line}")
except Exception:
    results.append(f"  migrate: FAILED\n{traceback.format_exc()}")

# --- Check DB file exists ---
db_path = os.path.join(probe_root, "probe_db.sqlite3")
results.append(f"\n[Database file]")
results.append(f"  Exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    results.append(f"  Size: {os.path.getsize(db_path)} bytes")

# --- CRUD ---
results.append("\n[CRUD operations]")
try:
    from testapp.models import Task

    # Create
    t = Task.objects.create(title="Probe task", done=False)
    results.append(f"  CREATE: SUCCESS (id={t.id}, title='{t.title}')")

    # Read
    fetched = Task.objects.get(id=t.id)
    results.append(f"  READ:   SUCCESS (title='{fetched.title}', done={fetched.done})")

    # Update
    fetched.done = True
    fetched.save()
    updated = Task.objects.get(id=t.id)
    results.append(f"  UPDATE: SUCCESS (done={updated.done})")

    # List
    count = Task.objects.count()
    results.append(f"  COUNT:  {count} task(s) in database")

    # Delete
    updated.delete()
    remaining = Task.objects.count()
    results.append(f"  DELETE: SUCCESS ({remaining} task(s) remaining)")

except Exception:
    results.append(f"  CRUD: FAILED\n{traceback.format_exc()}")

# --- Auth model (Django's built-in) ---
results.append("\n[Built-in auth model]")
try:
    from django.contrib.auth.models import User

    User.objects.create_user("probeuser", "probe@test.local", "probe123")
    user_count = User.objects.count()
    results.append(f"  Create user: SUCCESS ({user_count} user(s))")
    User.objects.filter(username="probeuser").delete()
    results.append(f"  Delete user: SUCCESS")
except Exception:
    results.append(f"  Auth model: FAILED\n{traceback.format_exc()}")

output = "\n".join(results)
print(output)

results_path = os.path.join(probe_root, "probe2_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 2 ===")
