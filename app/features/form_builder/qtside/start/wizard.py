"""The Wizard blank card (UX-CAT-015, R3-121 starts here).

The card is a QWizard root with two QWizardPage pages ("Step 1", "Step 2"), each
with a vertical layout. It lives here, not in ``engine/project/templates.py``:
the New form flow takes finished ``.ui`` text for it (``create_form`` writes the
writer's canonical form of that text), so the engine template table is unchanged.
"""

from __future__ import annotations

from app.features.form_builder.engine.project.form_xml import form_document
from app.features.form_builder.engine.project.templates import GROUP_BLANK, FormTemplate

WIZARD_KEY = "wizard"

WIZARD_CARD = FormTemplate(
    WIZARD_KEY,
    "Wizard",
    "Two steps with Back and Next.",
    GROUP_BLANK,
    "QWizard",
    True,
    None,
)


def _page(object_name: str, title: str, layout_name: str) -> str:
    return (
        '  <widget class="QWizardPage" name="%s">\n'
        '   <property name="title"><string>%s</string></property>\n'
        '   <layout class="QVBoxLayout" name="%s"/>\n'
        "  </widget>\n"
    ) % (object_name, title, layout_name)


def wizard_document(class_name: str) -> str:
    """The Wizard card's ``.ui`` text for a form named ``class_name``."""
    inner = _page("wizardPage", "Step 1", "verticalLayout") + _page("wizardPage_2", "Step 2", "verticalLayout_2")
    return form_document(class_name, "QWizard", inner)
