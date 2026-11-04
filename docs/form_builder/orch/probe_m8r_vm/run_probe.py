"""M8.R probe for the ChoreBoy VM.

Python 3.9. No pytest. Do not set QT_QPA_PLATFORM. Speed rows come from
tests.form_builder.perf.m8_paths. This file adds the PostgreSQL 9.3 invoice
demo, the Try rollback walk, and the section 13.5.11 facts.

The 1.0 image has PySide2 and no bundled database driver. The alias and the
pure-Python pg8000 tree are probe payload, not product code.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
WORK = Path(os.environ.get("CBCS_M8R_WORK", "/tmp/m8r_work"))
DSN = os.environ.get(
    "CBCS_M8R_DSN",
    "host=77.77.77.1 port=5432 user=postgres dbname=shop",
)


def _loadavg():
    try:
        return [round(value, 2) for value in os.getloadavg()], ""
    except OSError as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def _write(name, payload):
    RESULTS.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    path = RESULTS / name
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _fail(text):
    _write("error.txt", text)
    print(text, file=sys.stderr)
    return 1


def _import_status(name):
    try:
        module = __import__(name)
    except Exception as exc:
        return "%s: %s" % (type(exc).__name__, exc)
    return getattr(module, "__file__", "imported")


def _bundled_drivers():
    """Import from a clean AppRun, with the payload directory off sys.path."""

    script = (
        "import os, sys\n"
        "sys.path = [p for p in sys.path if 'm8r' not in p and 'payload' not in p]\n"
        "os.chdir('/tmp')\n"
        "out = {}\n"
        "for name in ('psycopg', 'pg8000'):\n"
        "    try:\n"
        "        module = __import__(name)\n"
        "        out[name] = getattr(module, '__file__', 'imported')\n"
        "    except Exception as exc:\n"
        "        out[name] = '%s: %s' % (type(exc).__name__, exc)\n"
        "print(repr(out))\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("QT_QPA_PLATFORM", None)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        proc = subprocess.run(
            ["/opt/freecad/AppRun", "-c", script],
            cwd="/tmp",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}
    text = proc.stdout.decode("utf-8", "replace")
    for line in reversed(text.splitlines()):
        if line.startswith("{") and line.endswith("}"):
            try:
                return ast.literal_eval(line)
            except Exception:
                break
    return {"raw": text[-500:], "code": proc.returncode}


def _rss_kb():
    try:
        for line in open("/proc/self/status", encoding="utf-8"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError as exc:
        return "%s: %s" % (type(exc).__name__, exc)
    return None


def _attr():
    try:
        return open("/proc/self/attr/current", encoding="utf-8", errors="replace").read().strip()
    except OSError as exc:
        return "%s: %s" % (type(exc).__name__, exc)


def _ensure_shop(fields):
    from tests.form_builder.perf.m8_paths import _connect_postgres, parse_dsn

    del parse_dsn
    admin = dict(fields)
    admin["dbname"] = "postgres"
    connection = _connect_postgres(admin)
    connection.autocommit = True
    cursor = connection.cursor()
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (fields.get("dbname") or "shop",))
    if cursor.fetchone() is None:
        cursor.execute("CREATE DATABASE %s" % (fields.get("dbname") or "shop",))
    connection.close()


def _sql(fields, statement, params=()):
    from tests.form_builder.perf.m8_paths import _connect_postgres

    connection = _connect_postgres(fields)
    cursor = connection.cursor()
    cursor.execute(statement, params)
    try:
        rows = cursor.fetchall()
    except Exception:
        rows = []
    connection.commit()
    connection.close()
    return rows


def _md5(fields):
    invoices = _sql(
        fields,
        "SELECT md5(COALESCE(string_agg("
        "id::text || '|' || invoice_no || '|' || COALESCE(notes, '') || '|' || COALESCE(total::text, ''), "
        "E'\\n' ORDER BY id), '')) FROM invoices",
    )
    lines = _sql(
        fields,
        "SELECT md5(COALESCE(string_agg("
        "id::text || '|' || invoice_id::text || '|' || line_no::text || '|' || "
        "COALESCE(qty::text, '') || '|' || COALESCE(price::text, ''), "
        "E'\\n' ORDER BY id), '')) FROM invoice_lines",
    )
    return {
        "invoices": None if not invoices else invoices[0][0],
        "invoice_lines": None if not lines else lines[0][0],
    }


def _driver_facts(fields):
    facts = {"bundled": _bundled_drivers()}
    sys.path.insert(0, str(HERE))
    facts["on_probe_path"] = {"psycopg": _import_status("psycopg"), "pg8000": _import_status("pg8000")}
    notes = {}
    try:
        from tests.form_builder.perf.m8_paths import LAST_DRIVER, _connect_postgres

        connection = _connect_postgres(fields)
        cursor = connection.cursor()
        cursor.execute("SET client_encoding TO 'UTF8'")
        cursor.execute("SHOW client_encoding")
        shown = cursor.fetchone()
        notes["client_encoding"] = None if shown is None else shown[0]
        cursor.execute("CREATE TEMP TABLE m8r_returning (id serial PRIMARY KEY, name text)")
        cursor.execute("INSERT INTO m8r_returning (name) VALUES (%s) RETURNING id", ("probe",))
        row = cursor.fetchone()
        notes["returning_id"] = None if row is None else row[0]
        notes["driver"] = LAST_DRIVER
        connection.rollback()
        connection.close()
    except Exception:
        notes["error"] = traceback.format_exc()
    try:
        hba = _sql(fields, "SELECT setting FROM pg_settings WHERE name = 'hba_file'")
        notes["hba_file"] = None if not hba else hba[0][0]
    except Exception as exc:
        notes["hba_file"] = "%s: %s" % (type(exc).__name__, exc)
    notes["wrong_password"] = _wrong_password(fields)
    facts["postgres"] = notes
    return facts


def _wrong_password(fields):
    from tests.form_builder.perf.m8_paths import _connect_postgres

    trial = dict(fields)
    trial["password"] = "not-the-password"
    try:
        connection = _connect_postgres(trial)
        connection.close()
    except Exception as exc:
        return "rejected: %s" % exc
    return "accepted"


def _machine_file():
    from app.features.form_builder.engine.data.machine import MachineEntry, save_machine

    project = WORK / "machine_project"
    folder = WORK / "machine_file"
    project.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "shop.json"
    save_machine(str(path), (("shop", MachineEntry(password="m8r")),), project_root=str(project))
    file_mode = os.stat(path).st_mode & 0o777
    dir_mode = os.stat(folder).st_mode & 0o777
    return {
        "path": str(path),
        "file_mode": oct(file_mode),
        "dir_mode": oct(dir_mode),
        "file_is_0600": file_mode == 0o600,
        "dir_is_0700": dir_mode == 0o700,
        "writable": os.access(str(folder), os.W_OK),
    }


def _grab(widget, name):
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    widget.show()
    widget.raise_()
    widget.resize(960, 640)
    if app is not None:
        app.processEvents()
    pixmap = widget.grab()
    if pixmap.width() > 800:
        height = int(round(pixmap.height() * (800.0 / float(pixmap.width()))))
        pixmap = pixmap.scaled(800, max(height, 1))
    path = RESULTS / name
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError("grab failed for %s" % name)
    return path.stat().st_size


def _demo(fields):
    from tests.form_builder.perf.m8_paths import LAST_DRIVER, _Host

    root = WORK / "pg_proj"
    notes = {"rss_before_kb": _rss_kb()}
    listing = _Host(root, "customer_list", "")
    invoice = _Host(root, "invoice", "")
    try:
        listing.open()
        notes["list_bytes"] = _grab(listing.widget, "01_list.png")
        listing.ui.searchEdit.setText("Customer 1")
        listing.ui.cbcs_refresh_list()
        notes["search_bytes"] = _grab(listing.widget, "02_search.png")
        model = listing.ui.resultTable.model()
        notes["search_rows"] = 0 if model is None else int(model.rowCount())
    finally:
        listing.close()
    try:
        invoice.open()
        invoice.ui.cbcs_open(1)
        notes["invoice_bytes"] = _grab(invoice.widget, "03_invoice.png")
        notes["lookup_bytes"] = _grab(invoice.widget, "04_lookup.png")
        invoice.ui._cbcs_add_row()
        model = invoice.ui.invoice_linesView.model()
        row = model.rowCount() - 1
        role = invoice.ui._cbcs_line_role
        model.item(row, 0).setData(1, role)
        model.item(row, 1).setText("probe line")
        model.item(row, 2).setData(1, role)
        model.item(row, 3).setData(1, role)
        notes["add_bytes"] = _grab(invoice.widget, "05_add_line.png")
        notes["saved"] = bool(invoice.ui.cbcs_save())
        notes["save_bytes"] = _grab(invoice.widget, "06_saved.png")
        module = sys.modules.get("cbcs_connections")
        open_map = getattr(module, "_OPEN", {})
        raw = open_map.get("shop")
        prepared = None
        if raw is not None:
            cursor = raw.cursor()
            cursor.execute("SELECT count(*) FROM pg_prepared_statements")
            prepared = cursor.fetchone()[0]
        notes["prepared_statements"] = prepared
        notes["driver"] = LAST_DRIVER
    finally:
        invoice.close()
    notes["rss_after_kb"] = _rss_kb()
    landed = _sql(
        fields,
        "SELECT line_no, product_id, description, qty, price::text "
        "FROM invoice_lines WHERE invoice_id = 1 ORDER BY line_no",
    )
    notes["invoice_1_lines"] = [
        {"line_no": item[0], "product_id": item[1], "description": item[2], "qty": item[3], "price": item[4]}
        for item in landed
    ]
    _write("demo.json", notes)
    return notes


def _try_walk(fields):
    from app.features.form_builder.engine.ipc.protocol import (
        PROTOCOL_NAME,
        PROTOCOL_VERSION,
        Appearance,
        Hello,
        TryConnectionSpec,
        TryDataPlan,
        TryStart,
        encode_frame,
    )
    from app.features.form_builder.qtside.preview.launch import preview_command

    before = _md5(fields)
    root = WORK / "pg_proj"
    source = (root / "forms" / "ui_invoice.py").read_text(encoding="utf-8")
    spec = TryConnectionSpec(
        name="shop",
        mode="rollback",
        title="Shop",
        engine="postgres",
        host=fields.get("host") or "77.77.77.1",
        port=int(fields.get("port") or "5432"),
        database=fields.get("dbname") or "shop",
        user=fields.get("user") or "postgres",
        password_policy="none",
    )
    message = TryStart(
        request_id="m8r-try",
        view_id="invoice",
        module_name="forms.ui_invoice",
        module_source=source,
        window_class_name="InvoiceWindow",
        base_class="QWidget",
        window_values=(),
        data=TryDataPlan(specs=(spec,)),
        show_form=True,
        run_behavior=True,
        form_path=str(root / "forms" / "invoice.ui"),
        ui_xml=(root / "forms" / "invoice.ui").read_text(encoding="utf-8"),
        project_root=str(root),
        sys_path=(str(root), str(HERE)),
        appearance=Appearance(),
    )
    hello = Hello(
        request_id="m8r-hello",
        protocol=PROTOCOL_NAME,
        version=PROTOCOL_VERSION,
        session_token="m8r",
        host_pid=os.getpid(),
    )
    for name in ("try_walk.done", "try_error.txt", "try_walk.json"):
        path = RESULTS / name
        if path.exists():
            path.unlink()
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    env.pop("CBCS_QT_API", None)
    env["CBCS_PROBE_RESULTS"] = str(RESULTS)
    env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get("PYTHONPATH", "")
    command = preview_command(str(HERE))
    frame_path = Path("/tmp/m8r_try_frame.txt")
    frame_path.write_text(encode_frame(hello) + encode_frame(message), encoding="utf-8")
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        cwd=str(HERE),
        env=env,
    )
    deadline = time.monotonic() + 40
    done_paths = (RESULTS / "try_walk.done", Path("/tmp/m8r_try_results/try_walk.done"))
    while time.monotonic() < deadline and not any(path.is_file() for path in done_paths):
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
    stderr = b""
    try:
        stderr = proc.stderr.read() if proc.stderr is not None else b""
    except Exception:
        stderr = b""
    _write("try_child_stderr.txt", stderr.decode("utf-8", "replace")[-8000:])
    for name in ("try_walk.json", "try_error.txt", "try_banner.txt", "what_ran.txt", "try_walk.done", "child_started.txt", "try_names.txt", "try_load.txt", "push.txt", "07_try_banner.png", "08_what_ran.png", "dialog.txt"):
        source = Path("/tmp/m8r_try_results") / name
        if source.is_file():
            (RESULTS / name).write_bytes(source.read_bytes())
    after = _md5(fields)
    walk = {}
    path = RESULTS / "try_walk.json"
    if path.is_file():
        walk = json.loads(path.read_text(encoding="utf-8"))
    banner = ""
    banner_path = RESULTS / "try_banner.txt"
    if banner_path.is_file():
        banner = banner_path.read_text(encoding="utf-8")
    ran = ""
    ran_path = RESULTS / "what_ran.txt"
    if ran_path.is_file():
        ran = ran_path.read_text(encoding="utf-8")
    return {
        "command0": command[0] if command else "",
        "before": before,
        "after": after,
        "md5_unchanged": before == after,
        "banner": banner or walk.get("banner") or "",
        "what_ran": ran or walk.get("what_ran") or "",
        "saved": walk.get("saved"),
        "error": walk.get("error") or ((RESULTS / "try_error.txt").read_text(encoding="utf-8") if (RESULTS / "try_error.txt").is_file() else ""),
        "exit": proc.poll(),
    }


def main():
    import app.qt.qt_compat
    import pyside6_alias

    pyside6_alias.install()
    from tests.form_builder.perf import m8_paths

    if Path("/tmp/m8r_only_try").is_file():
        fields = m8_paths.parse_dsn(DSN)
        facts = {"try_only": _try_walk(fields)}
        _write("facts_try.json", facts)
        return 0

    RESULTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    load, load_error = _loadavg()
    facts = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "loadavg": load,
        "loadavg_error": load_error,
        "apparmor_attr": _attr(),
        "rss_kb": _rss_kb(),
    }
    fields = m8_paths.parse_dsn(DSN)
    try:
        facts["drivers"] = _driver_facts(fields)
        facts["machine_file"] = _machine_file()
        _ensure_shop(fields)
        code = m8_paths.main(["--machine", "vm", "--dsn", DSN, "--work", str(WORK), "--results", str(RESULTS)])
        facts["speed_exit"] = code
        if code != 0:
            error_path = RESULTS / "error.txt"
            facts["speed_error"] = error_path.read_text(encoding="utf-8") if error_path.is_file() else "speed exit %s" % code
            _write("facts.json", facts)
            return code
        summary_path = RESULTS / "summary_vm.json"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            helper = (summary.get("recorded") or {}).get("schema_helper_30") or {}
            facts["helper"] = {
                "p95_ms": helper.get("p95_ms"),
                "wall_p95_ms": helper.get("wall_p95_ms"),
                "command0": helper.get("command0"),
                "helper_script": helper.get("helper_script"),
                "evidence": helper.get("evidence"),
                "error": helper.get("error"),
            }
        facts["md5_before_try"] = _md5(fields)
        facts["try"] = _try_walk(fields)
        facts["demo"] = _demo(fields)
    except Exception:
        facts["error"] = traceback.format_exc()
        _write("facts.json", facts)
        print(facts["error"], file=sys.stderr)
        return 1
    _write("facts.json", facts)
    return 0 if not facts.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
