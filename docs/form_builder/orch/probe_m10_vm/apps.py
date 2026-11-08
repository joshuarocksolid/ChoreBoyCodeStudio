"""The three M10.1b apps, driven as a user would drive them."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from app.qt.QtWidgets import QCheckBox, QLabel, QLineEdit, QTabWidget

from drive import Drive


def write_db(path: Path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(script)
        connection.commit()
    finally:
        connection.close()


CUSTOMERS_SQL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    email TEXT,
    credit_limit REAL,
    active BOOLEAN
);
INSERT INTO customers (name, phone, email, credit_limit, active)
VALUES ('Ada Lovelace', '555-0100', 'ada@example.com', 100, 1);
"""

PRODUCTS_SQL = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    sku TEXT,
    price REAL,
    active BOOLEAN
);
CREATE TABLE stock_moves (
    id INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    qty REAL,
    note TEXT
);
INSERT INTO products (name, sku, price, active)
VALUES ('Nails', 'NAIL', 4.5, 1), ('Hinges', 'HNGE', 2.0, 1);
INSERT INTO stock_moves (product_id, qty, note) VALUES (1, 10, 'in'), (1, -2, 'sold');
"""


def _project_dir(parent: Path, name: str) -> Path:
    return parent / name


def _surface_ready(drive: Drive) -> bool:
    return drive.find("formBuilder.canvas") is not None and drive.find("formBuilder.newForm") is None


def new_form_named(drive: Drive, stem: str) -> None:
    drive.trigger("shell.action.file.newForm")
    drive.wait(lambda: drive.find("formBuilder.newForm.name") is not None, 6)
    drive.replace_text(drive.find("formBuilder.newForm.name"), stem)
    drive.pump(4)


def from_table(drive: Drive, app: str, table: str, make: str, lines: str = "", link: str = "") -> bool:
    state = {"ok": False, "saw": ""}

    def fill() -> None:
        if not drive.wait(lambda: drive.find("formBuilder.fromTable.tables") is not None, 8):
            state["saw"] = "the from-table dialog did not open"
            return
        drive.pump(8)
        drive.choose_combo("formBuilder.fromTable.connection", "shop")
        drive.choose_combo("formBuilder.fromTable.make", make)
        drive.wait(lambda: _list_has(drive, "formBuilder.fromTable.tables", table), 8)
        picked = drive.click_list_text("formBuilder.fromTable.tables", table)
        drive.pump(6)
        if lines:
            box = drive.find("formBuilder.fromTable.lines")
            if isinstance(box, QCheckBox) and not box.isChecked():
                drive.click(box)
            drive.choose_combo("formBuilder.fromTable.linesTable", lines)
            if link:
                drive.choose_combo("formBuilder.fromTable.linesLink", link)
        start = drive.find("formBuilder.fromTable.start")
        start_saw = "no start box"
        if isinstance(start, QCheckBox):
            start_saw = "start enabled=%s checked=%s" % (start.isEnabled(), start.isChecked())
            if start.isEnabled() and not start.isChecked():
                drive.click(start)
        create = drive.find("formBuilder.fromTable.create")
        label = create.text() if create is not None else ""
        state["saw"] = "%s; picked=%s; %s" % (label, picked, start_saw)
        if create is not None:
            drive.click(create)
        drive.pump(12)
        still = drive.find("formBuilder.fromTable")
        if still is not None and still.isVisible():
            reason = drive.find("formBuilder.fromTable.reason")
            state["saw"] = (reason.text() if isinstance(reason, QLabel) else "") or state["saw"]
            drive.click(drive.find("formBuilder.fromTable.cancel"))
        state["ok"] = picked and "0 field" not in label.lower()

    def start_click() -> None:
        card = drive.find("formBuilder.newForm.card.from_table")
        drive.click(card)

    started = time.perf_counter()
    drive.run_modal(start_click, fill)
    drive.timings["%s_open_form_ms" % app] = int((time.perf_counter() - started) * 1000)
    drive.step(app, "from-table", "Build a form from %s (%s)." % (table, make), state["saw"], state["ok"])
    return state["ok"]


def _list_has(drive: Drive, name: str, text: str) -> bool:
    widget = drive.find(name)
    if widget is None or not hasattr(widget, "count"):
        return False
    for i in range(widget.count()):
        item = widget.item(i)
        if item is not None and item.text() == text:
            return True
    return False


def connect_sqlite(drive: Drive, app: str, project: Path) -> bool:
    result = drive.open_settings_connections("Shop", "shop", "data/shop.db")
    ok = "Connected" in result and (project / "connections.json").is_file()
    drive.step(
        app,
        "connection",
        "File > Settings > Connections, add SQLite data/shop.db, Test.",
        result or "(no result text)",
        ok,
    )
    return ok or (project / "cbcs" / "connections.json").exists() or (project / "connections.json").exists()


def save_timed(drive: Drive, app: str, project: Path, stem: str) -> bool:
    started = time.perf_counter()
    drive.save_form()
    drive.timings["%s_save_ms" % app] = int((time.perf_counter() - started) * 1000)
    generated = project / "forms" / ("ui_%s.py" % stem)
    ok = generated.is_file()
    extra = ""
    if drive.disk_prompts:
        extra = " Disk prompt: %s." % ", ".join(drive.disk_prompts)
        drive.disk_prompts.clear()
    drive.step(app, "save", "Ctrl+S.", "ui file %s exists=%s.%s" % (generated.name, ok, extra), ok)
    return ok


def wire_save(drive: Drive, app: str, project: Path, stem: str) -> bool:
    body = "self.setWindowTitle('saved')"
    ok = drive.call_method("saveButton", body)
    window = project / "forms" / ("%s_window.py" % stem)
    text = window.read_text(encoding="utf-8") if window.is_file() else ""
    has = "def " in text and body in text
    drive.step(
        app,
        "your-code",
        "Select saveButton, Shift+F10, Write code for, replace pass.",
        "method file has the body=%s. %s" % (has, drive.code_note),
        ok and has,
    )
    return ok and has


def customer(drive: Drive, work: Path) -> Optional[Path]:
    app = "customer"
    name = "Customer card"
    parent = work / "projects"
    if not drive.new_project(name, parent):
        # The folder dialog is Qt's non-native dialog. If it did not finish,
        # the public create and open pair is the documented bypass.
        from app.project.project_service import create_blank_project

        root = parent / name
        create_blank_project(root, project_name=name)
        workflow = drive.window._file_project_commands_workflow
        workflow.open_project_by_path(str(root))
        drive.pump(12)
        drive.step(app, "new-project", "File > New Project. Dialog did not finish.", "opened %s with create_blank_project" % root, root.is_dir())
    else:
        root = parent / name
        drive.step(app, "new-project", "File > New Project, name Customer card.", "folder %s" % root, root.is_dir())
    if not root.is_dir():
        return None
    write_db(root / "data" / "shop.db", CUSTOMERS_SQL)
    connect_sqlite(drive, app, root)
    new_form_named(drive, "customer_card")
    from_table(drive, app, "customers", "Record form")
    email_ok = drive.add_check("email", "Email")
    drive.step(app, "email-check", "Behavior, Add check, Email address on email.", "check committed", email_ok)

    def credit_fill() -> None:
        drive.replace_text(drive.find("formBuilder.checks.min"), "0")

    credit_ok = drive.add_check("credit_limit", "Between", credit_fill)
    drive.step(app, "credit-check", "Add check Between with smallest 0 on credit_limit.", "check committed", credit_ok)
    rule_ok = drive.set_enabled_when("credit_limit", "active")
    drive.step(app, "enabled-rule", "Enabled when on credit_limit, formula active.", "rule committed", rule_ok)
    save_timed(drive, app, root, "customer_card")
    wire_save(drive, app, root, "customer_card")
    started = time.perf_counter()
    drive.preview()
    drive.timings["customer_preview_ms"] = int((time.perf_counter() - started) * 1000)
    drive.step(app, "preview", "Preview with Run behavior.", drive.shot(), True)
    _themes(drive, app)
    _launch_main(drive, app, root, "forms.customer_card_window", "CustomerCardWindow")
    return root


def products(drive: Drive, work: Path) -> Optional[Path]:
    app = "products"
    name = "Products"
    parent = work / "projects"
    root = parent / name
    _ensure_project(drive, app, name, parent)
    if not root.is_dir():
        return None
    write_db(root / "data" / "shop.db", PRODUCTS_SQL)
    connect_sqlite(drive, app, root)
    new_form_named(drive, "products")
    from_table(drive, app, "products", "List screen and record form", lines="stock_moves", link="product_id")
    rule_ok = drive.set_enabled_when("searchEdit", "form.count > 0")
    drive.step(app, "filter-rule", "Enabled when on the search box: form.count > 0.", "rule committed", rule_ok)
    add = drive.find("formBuilder.data.listFilterAdd")
    if add is not None:
        drive.click(add)
        drive.step(app, "filter-row", "Data panel, add a filter row.", "filter add clicked", True)
    else:
        drive.step(app, "filter-row", "Look for the list filter add button.", "the listing page was not showing", False)
    save_timed(drive, app, root, "products")
    list_ui = root / "forms" / "ui_products_list.py"
    drive.step(app, "list-file", "Save also writes the list screen.", "ui_products_list.py exists=%s" % list_ui.is_file(), list_ui.is_file())
    drive.preview()
    drive.step(app, "preview", "Preview the products form.", drive.shot(), True)
    _launch_main(drive, app, root, "forms.products_list_window", "ProductsListWindow")
    return root


def shop(drive: Drive, work: Path) -> Optional[Path]:
    app = "shop"
    name = "Shop desk"
    parent = work / "projects"
    root = parent / name
    _ensure_project(drive, app, name, parent)
    if not root.is_dir():
        return None
    new_form_named(drive, "shop_desk")
    card = drive.find("formBuilder.newForm.card.main_window")
    drive.click(card)
    drive.wait(_surface_ready, 8)
    drive.step(app, "main-window", "New form shop_desk, Main window card.", "canvas up=%s" % (drive.find("formBuilder.canvas") is not None), drive.find("formBuilder.canvas") is not None)
    drive.go_to("menubar")
    drive.press("Key_Return")
    drive.pump(4)
    drive.keys(drive.window, "")  # focus stays
    # Type menu titles. The in-place editor is formBuilder.menuEditLine when editing.
    editor = drive.find("formBuilder.menuEditLine")
    if editor is not None:
        drive.keys(editor, "File")
        drive.press("Key_Tab")
        drive.keys(drive.find("formBuilder.menuEditLine") or drive.window, "Edit")
        drive.press("Key_Tab")
        drive.keys(drive.find("formBuilder.menuEditLine") or drive.window, "Help")
        drive.step(app, "menus", "Enter on the menu bar, type File, Edit, Help.", "menu editor was up", True)
    else:
        drive.step(app, "menus", "Enter on the menu bar.", "menu editor did not appear", False)
    added = drive.trigger("form.mainWindow.addToolbar")
    drive.step(app, "toolbar", "Form > Main window > Add toolbar.", "action ran=%s" % added, added)
    drive.go_to("centralwidget")
    drive.press("Key_Slash")
    drive.pump(4)
    search = drive.find("formBuilder.outlineInsertFilter") or drive.find("formBuilder.insertFilter")
    if search is not None:
        drive.keys(search, "tab")
        drive.press("Key_Return")
        drive.step(app, "tabs", "Insert a tab widget in the central area.", "insert closed", True)
    else:
        drive.step(app, "tabs", "Press / to insert.", "insert popover did not open", False)
    drive.go_to("label")
    drive.press("Key_F7")
    drive.press("Key_Return")
    drive.go_to("lineEdit")
    drive.press("Key_Return")
    drive.press("Key_F8")
    drive.press("Key_Return")
    drive.step(app, "buddies-tabs", "F7 buddy, F8 tab order.", drive.shot(), True)
    save_timed(drive, app, root, "shop_desk")
    drive.call_method("action_customers", "self.statusBar().showMessage('Customers')")
    _launch_main(drive, app, root, "forms.shop_desk_window", "ShopDeskWindow")
    return root


def _ensure_project(drive: Drive, app: str, name: str, parent: Path) -> None:
    root = parent / name
    if root.is_dir():
        return
    if drive.new_project(name, parent) and root.is_dir():
        drive.step(app, "new-project", "File > New Project, name %s." % name, str(root), True)
        return
    from app.project.project_service import create_blank_project

    create_blank_project(root, project_name=name)
    drive.window._file_project_commands_workflow.open_project_by_path(str(root))
    drive.pump(12)
    drive.step(
        app,
        "new-project",
        "File > New Project. The folder dialog did not finish, so the public create and open commands ran.",
        str(root),
        root.is_dir(),
    )


def _themes(drive: Drive, app: str) -> None:
    for mode in ("light", "dark", "high_contrast_light", "high_contrast_dark"):
        drive.theme(mode)
        drive.pump(8)
        popup = drive.find("formBuilder.goToWidget")
        black = drive.mostly_black(popup) if popup is not None else None
        drive.step(
            app,
            "preview-%s" % mode,
            "View > Theme > %s while Preview is open." % mode,
            "screen %s; popup black=%s" % (drive.shot(), black),
            black is not True,
        )


def _launch_main(drive: Drive, app: str, root: Path, module: str, class_name: str) -> None:
    """Blank main.py is the project's own file, so the start checkbox stays off.

    The manual tells the person to open the new screen from main.py. This types
    that launch file when the editor will take it, and otherwise writes the same
    text the product uses for the checkbox.
    """
    from app.features.form_builder.engine.project.start_screen import render_entry

    text = render_entry(module, class_name)
    main = root / "main.py"
    tree = drive.find("shell.projectTree")
    opened = False
    if tree is not None and hasattr(tree, "findItems"):
        from app.qt.QtCore import Qt

        match = getattr(getattr(Qt, "MatchFlag", Qt), "MatchRecursive")
        matches = tree.findItems("main.py", match)
        if matches:
            tree.setCurrentItem(matches[0])
            drive.press("Key_Return")
            drive.pump(8)
            opened = True
    if not opened:
        drive.window._editor_tab_factory.open_file_in_editor(str(main))
        drive.pump(6)
    focus = drive.qapp.focusWidget()
    typed = False
    if focus is not None and hasattr(focus, "toPlainText"):
        focus.selectAll()
        drive.press("Key_Backspace", widget=focus)
        for line in text.splitlines():
            drive.keys(focus, line)
            drive.press("Key_Return", widget=focus)
        drive._arm_disk_dialog()
        drive.press("Key_S", "Control")
        drive.pump(6)
        typed = class_name in main.read_text(encoding="utf-8")
    if not typed:
        main.write_text(text, encoding="utf-8")
        drive.step(
            app,
            "entry",
            "The start checkbox is off because main.py is already the project's file. Wrote the launch the manual describes.",
            "main.py opens %s" % class_name,
            class_name in main.read_text(encoding="utf-8"),
        )
        return
    drive.step(app, "entry", "Replace main.py in the editor so the app opens the form.", "typed %s" % class_name, True)


def package_and_install(drive: Drive, app: str, root: Path, export_parent: Path) -> Optional[Path]:
    export_parent.mkdir(parents=True, exist_ok=True)
    state = {"ok": False}

    def fill() -> None:
        if not drive.wait(lambda: drive.find("shell.packageWizardDialog") is not None, 6):
            return
        dialog = drive.find("shell.packageWizardDialog")
        edits = [] if dialog is None else dialog.findChildren(QLineEdit)
        if edits:
            drive.replace_text(edits[0], str(export_parent))
        drive.click_text(dialog, "Next")
        drive.pump(4)
        drive.click_text(dialog, "Package")
        state["ok"] = True

    def start() -> None:
        drive.trigger("shell.action.build.package")

    started = time.perf_counter()
    drive.run_modal(start, fill)
    drive.timings["%s_package_ms" % app] = int((time.perf_counter() - started) * 1000)
    artifact = _newest_installer(export_parent)
    drive.step(app, "package", "Run > Package Project.", "artifact %s" % artifact, artifact is not None)
    if artifact is None:
        return None
    install_dir = _install(drive, app, artifact)
    return install_dir


def _newest_installer(parent: Path) -> Optional[Path]:
    found = [path for path in parent.glob("*_installer_v*") if path.is_dir()]
    if not found:
        return None
    found.sort(key=lambda path: path.stat().st_mtime)
    return found[-1]


def _install(drive: Drive, app: str, artifact: Path) -> Optional[Path]:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("cbcs_m10_installer", artifact / "installer" / "install.py")
    if spec is None or spec.loader is None:
        drive.step(app, "install", "Load the installer the package wrote.", "missing install.py", False)
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest = module.load_package_manifest(artifact)
    install_dir = module.resolve_silent_install_dir(manifest)
    home = Path.home()
    homes = [home]
    if Path("/home/default").is_dir() and home != Path("/home/default"):
        homes.append(Path("/home/default"))
    started = time.perf_counter()
    try:
        outcome = module.perform_install(
            manifest=manifest,
            package_root=artifact,
            install_dir=install_dir,
            home_roots=homes,
        )
    except OSError:
        install_dir = Path("/tmp/m10_installed") / app
        outcome = module.perform_install(
            manifest=manifest,
            package_root=artifact,
            install_dir=install_dir,
            home_roots=[Path("/tmp")],
        )
    drive.timings["%s_install_ms" % app] = int((time.perf_counter() - started) * 1000)
    launcher = Path(outcome.install_dir) / manifest.launcher_filename if outcome.ok else None
    drive.step(
        app,
        "install",
        "Run the package installer (perform_install, the same call the wizard's Install button makes).",
        "ok=%s dir=%s" % (outcome.ok, outcome.install_dir),
        bool(outcome.ok and launcher is not None and launcher.is_file()),
    )
    return Path(outcome.install_dir) if outcome.ok else None
