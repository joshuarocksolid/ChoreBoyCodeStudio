#!/usr/bin/env python
"""
Probe 9: Django REST Framework import and serialization
Tests whether vendored DRF can import, configure, and serialize data
under this Python runtime.  No HTTP involved -- isolates import/setup
issues from network issues.
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

results = []


def check(label, fn):
    try:
        val = fn()
        results.append(f"  {label}: YES ({val})")
        return True
    except Exception:
        results.append(f"  {label}: FAILED\n{traceback.format_exc()}")
        return False


print("=== Probe 9: DRF Import & Serialization ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")

results.append("\n[DRF import]")
check("rest_framework", lambda: __import__("rest_framework").VERSION)

results.append("\n[Django setup with DRF settings]")
os.environ["DJANGO_SETTINGS_MODULE"] = "testsite.settings_drf"
settings_ok = False
try:
    import django
    django.setup()
    results.append("  django.setup(): SUCCESS")

    from django.conf import settings as _settings
    active_module = _settings.SETTINGS_MODULE
    results.append(f"  Active settings module: {active_module}")
    if active_module != "testsite.settings_drf":
        results.append(f"  WARNING: Django was already initialized with '{active_module}'")
        results.append(f"  DB-dependent tests will use that config, not settings_drf.")
        results.append(f"  Run this probe in a fresh AppRun process to avoid contamination.")
    else:
        settings_ok = True
except Exception:
    results.append(f"  django.setup(): FAILED\n{traceback.format_exc()}")

results.append("\n[DRF core imports]")
check("serializers module", lambda: "ok" if __import__("rest_framework.serializers") else "fail")
check("viewsets module", lambda: "ok" if __import__("rest_framework.viewsets") else "fail")
check("routers module", lambda: "ok" if __import__("rest_framework.routers") else "fail")
check("renderers module", lambda: "ok" if __import__("rest_framework.renderers") else "fail")
check("parsers module", lambda: "ok" if __import__("rest_framework.parsers") else "fail")
check("status module", lambda: "ok" if __import__("rest_framework.status") else "fail")

results.append("\n[Serializer round-trip: dict input]")
try:
    from testapp.serializers import TaskSerializer

    data = {"title": "Probe 9 task", "done": False}
    ser = TaskSerializer(data=data)
    valid = ser.is_valid()
    results.append(f"  is_valid(): {valid}")
    if valid:
        results.append(f"  validated_data: {ser.validated_data}")
    else:
        results.append(f"  errors: {ser.errors}")
except Exception:
    results.append(f"  Serializer (dict): FAILED\n{traceback.format_exc()}")

results.append("\n[Serializer round-trip: model instance]")
if not settings_ok:
    results.append("  SKIPPED: Django initialized with wrong settings (see warning above)")
    results.append("  Re-run in a fresh AppRun process for this test.")
else:
    try:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("migrate", verbosity=0, stdout=out)
        results.append(f"  migrate: SUCCESS")

        from testapp.models import Task

        obj = Task.objects.create(title="Probe 9 model task", done=True)
        ser = TaskSerializer(obj)
        results.append(f"  serialized data: {ser.data}")
        obj.delete()
        results.append(f"  cleanup: deleted test object")
    except Exception:
        results.append(f"  Serializer (model): FAILED\n{traceback.format_exc()}")

results.append("\n[Router URL generation]")
try:
    from rest_framework.routers import DefaultRouter

    from testapp.views_api import TaskViewSet

    router = DefaultRouter()
    router.register(r"tasks", TaskViewSet)
    urls = router.get_urls()
    url_names = [u.name for u in urls if hasattr(u, "name")]
    results.append(f"  Generated {len(urls)} URL patterns")
    results.append(f"  Named patterns: {url_names}")
except Exception:
    results.append(f"  Router: FAILED\n{traceback.format_exc()}")

results.append("\n[ViewSet inspection]")
try:
    from testapp.views_api import TaskViewSet

    actions = ["list", "create", "retrieve", "update", "partial_update", "destroy"]
    available = [a for a in actions if hasattr(TaskViewSet, a)]
    results.append(f"  Available actions: {available}")
except Exception:
    results.append(f"  ViewSet: FAILED\n{traceback.format_exc()}")

output = "\n".join(results)
print(output)

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)
results_path = os.path.join(results_dir, "probe9_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 9 ===")
