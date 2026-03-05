# Django ChoreBoy Probe Bundle

Self-contained test bundle to determine whether vendored Django 4.2 LTS
can run on the ChoreBoy system via FreeCAD AppRun.

## What's included

| File/Dir | Purpose |
|---|---|
| `vendor/` | Django 4.2.29, asgiref 3.11.1, sqlparse 0.5.5, typing_extensions 4.15.0, pg8000 1.31.5, django-pg8000 0.0.5, scramp 1.4.5, asn1crypto 1.5.1, python-dateutil 2.9.0, six 1.17.0, pytz, djangorestframework 3.16.1 |
| `testsite/` | Minimal Django project (settings, urls, settings_postgres, settings_drf, urls_drf) |
| `testapp/` | One-model app (Task) with pre-generated migration |
| `manage.py` | Django management entrypoint (vendor path pre-configured) |
| `probe1_import.py` | Can Django import and `setup()` under AppRun? |
| `probe2_orm.py` | Can Django run migrations and do CRUD with SQLite? |
| `probe3_commands.py` | Do management commands work? |
| `probe4_qt_integration.py` | Can Django ORM + PySide2 Qt UI coexist? (critical) |
| `probe5_port_binding.py` | Can we bind localhost ports? (informational) |
| `probe6_pg8000_raw.py` | Can vendored pg8000 connect to PostgreSQL and do CRUD? |
| `probe7_django_postgres.py` | Can Django ORM work against PostgreSQL via django-pg8000? |
| `probe8_pg_benchmark.py` | PostgreSQL vs SQLite performance benchmarks |
| `probe9_drf_import.py` | Can DRF import, setup, and serialize under AppRun? |
| `probe10_drf_api.py` | Can DRF serve a JSON API via runserver and be consumed over HTTP? |

## How to run on ChoreBoy

### 1. Copy the bundle

Copy the entire `django_probe/` folder to ChoreBoy, for example:

```
/home/default/django_probe/
```

### 2. Run probes in order

Each probe is self-contained. Run them via AppRun in a terminal:

**Probe 1 -- Django import:**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe1_import.py',run_name='__main__')"
```

**Probe 2 -- ORM and CRUD (run after probe 1 passes):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe2_orm.py',run_name='__main__')"
```

**Probe 3 -- Management commands (run after probe 2 passes):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe3_commands.py',run_name='__main__')"
```

**Probe 4 -- Django + PySide2 Qt integration (the big one):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe4_qt_integration.py',run_name='__main__')"
```

This will open a Qt window showing a table of tasks from the Django ORM.
Close the window to end the probe.

**Probe 5 -- Port binding (informational):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe5_port_binding.py',run_name='__main__')"
```

### 3. Run PostgreSQL probes

Probes 6-8 require PostgreSQL running on `localhost:5432`. These probes
test connectivity, Django ORM integration, and performance using the
vendored pg8000 pure-Python driver.

**Prerequisite:** PostgreSQL must be running on `localhost:5432` with
user `postgres`, password `true`. Probe 6 will create the `django_probe`
database if it does not exist.

**Probe 6 -- Raw pg8000 connectivity (run first):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe6_pg8000_raw.py',run_name='__main__')"
```

**Probe 7 -- Django ORM + PostgreSQL (run after probe 6 passes):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe7_django_postgres.py',run_name='__main__')"
```

**Probe 8 -- Performance benchmarks (run after probe 7 passes):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe8_pg_benchmark.py',run_name='__main__')"
```

### 4. Run DRF probes

Probes 9-10 test Django REST Framework as a local JSON API layer.
Probe 5 (port binding) should pass before running these.

**Probe 9 -- DRF import and serialization (run after probes 1-2 pass):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe9_drf_import.py',run_name='__main__')"
```

**Probe 10 -- DRF API serving and HTTP consumption (run after probe 9 passes):**
```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/django_probe';sys.path.insert(0,root);os.chdir(root);runpy.run_path('probe10_drf_api.py',run_name='__main__')"
```

This will start a Django runserver subprocess on port 8321, exercise full
CRUD over HTTP using stdlib urllib, then shut the server down.

### 5. Check results

Each probe prints results to stdout and writes a `probeN_results.txt` file
in the `results/` directory.

## Running as FreeCAD macros

Alternatively, you can paste probe scripts into FreeCAD's Python console.
Replace the `sys.path` bootstrap lines with:

```python
import sys, os
root = "/home/default/django_probe"
sys.path.insert(0, os.path.join(root, "vendor"))
sys.path.insert(0, root)
os.chdir(root)
```

Then paste the rest of the probe script.

## Decision matrix

### SQLite probes (1-5)

| Probe 1 | Probe 2 | Probe 3 | Probe 4 | Probe 5 | Verdict |
|---|---|---|---|---|---|
| PASS | PASS | PASS | PASS | any | Django + PySide2 on ChoreBoy is fully viable |
| PASS | PASS | PASS | FAIL | any | Django ORM works but can't coexist with PySide2 (unlikely) |
| PASS | PASS | FAIL | any | any | ORM works, some commands broken (probably fine, investigate) |
| PASS | FAIL | any | any | any | Django loads but SQLite/ORM broken (check Python stdlib) |
| FAIL | any | any | any | any | Django can't initialize under AppRun's Python 3.9 (investigate errors) |

If probes 1-4 all pass, the path forward is:
**Django as a headless ORM/data layer with native PySide2 UI on ChoreBoy.**

### PostgreSQL probes (6-8)

| Probe 6 | Probe 7 | Probe 8 | Verdict |
|---|---|---|---|
| PASS | PASS | PASS | Django + PostgreSQL via pg8000 is fully viable on ChoreBoy |
| PASS | PASS | FAIL | Django+Postgres works but performance needs investigation |
| PASS | FAIL | any | pg8000 works raw but django-pg8000 backend has issues; consider custom backend |
| FAIL | any | any | pg8000 cannot connect to Postgres (check credentials, Postgres service, network) |

If probes 6-7 pass, Django can use PostgreSQL as a backend on ChoreBoy
via the vendored pg8000 pure-Python driver.

### DRF probes (9-10)

| Probe 9 | Probe 10 | Verdict |
|---|---|---|
| PASS | PASS | DRF as a local JSON API layer on ChoreBoy is fully viable |
| PASS | FAIL | DRF loads but runserver/HTTP has issues; investigate |
| FAIL | any | DRF cannot import/setup under AppRun Python 3.9.2; try DRF 3.14.x |

If probes 9-10 pass, ChoreBoy can host a local REST API that other
processes (PySide2 apps, scripts, browsers) can consume over localhost.

## Contents: vendored packages

All packages are pure Python (no compiled .so files). Verified compatible
with Python >= 3.9.

### Core Django stack
- Django 4.2.29 (LTS, supports Python 3.8-3.12)
- asgiref 3.11.1 (requires Python >= 3.9)
- sqlparse 0.5.5 (requires Python >= 3.8)
- typing_extensions 4.15.0 (required by asgiref on Python < 3.10)

### PostgreSQL connectivity
- pg8000 1.31.5 (pure-Python PostgreSQL driver, requires Python >= 3.9)
- django-pg8000 0.0.5 (Django database backend for pg8000)
- scramp 1.4.5 (SCRAM auth for pg8000, pinned for Python 3.9 compat)
- asn1crypto 1.5.1 (ASN.1 parsing for scramp)
- python-dateutil 2.9.0 (date handling for pg8000)
- six 1.17.0 (Python 2/3 compat, required by python-dateutil)
- pytz (timezone support)

### Django REST Framework
- djangorestframework 3.16.1 (pure-Python REST API framework, requires Python >= 3.9)

### Connector analysis

Only pg8000 satisfies all ChoreBoy constraints:

| Connector | Pure Python | Python 3.9 | No libpq | Django backend | Viable |
|---|---|---|---|---|---|
| pg8000 + django-pg8000 | Yes | Yes | Yes | Yes | **Yes** |
| psycopg3 pure mode | Yes | 3.2.x only | No (needs libpq) | Built-in | No |
| psycopg3 binary | No (.so) | No (3.10+) | Yes (bundled) | Built-in | No |
| pg-purepy | Yes | No (3.13+) | Yes | No | No |
