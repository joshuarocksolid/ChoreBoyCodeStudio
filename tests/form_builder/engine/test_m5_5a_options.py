"""Preview style and screen choices, and the code line index (M5.5a, UX-PREV-001, UX-PREV-004). Qt-free."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.integration import preview_options as po
from app.features.form_builder.integration.memory import PreviewOptionsStore, payload_with_preview, preview_from_payload
from app.features.form_builder.qtside.code_view.lines import CodeIndex

pytestmark = pytest.mark.unit

_GENERATED = """class Ui_Till(object):
    def setupUi(self, Till):
        if not Till.objectName():
            Till.setObjectName(u"Till")
        Till.resize(480, 320)
        self.mainLayout = QVBoxLayout(Till)
        self.mainLayout.setObjectName(u"mainLayout")
        self.totalLabel = QLabel(Till)
        self.totalLabel.setObjectName(u"totalLabel")
        self.mainLayout.addWidget(self.totalLabel)
        self.retranslateUi(Till)
        QMetaObject.connectSlotsByName(Till)

    def retranslateUi(self, Till):
        self.totalLabel.setText(QCoreApplication.translate(u"Till", u"Total", None))
"""


@pytest.mark.parity("R3-178")
def test_the_window_title_names_only_the_choices_that_are_not_the_default() -> None:
    plain = po.PreviewChoices()
    assert po.window_title("invoice.ui", plain, ()) == "Preview · invoice.ui"
    both = po.PreviewChoices(style="Windows", screen="Small screen")
    assert po.window_title("invoice.ui", both, ()) == "Preview · invoice.ui · Windows style · Small screen"
    mine = po.clean_profile("Till 2", 800, 600)
    chosen = po.PreviewChoices(screen="Till 2")
    assert po.window_title("a.ui", chosen, (mine,)) == "Preview · a.ui · Till 2"


@pytest.mark.parity("R3-179")
def test_the_menu_texts_are_the_spec_texts() -> None:
    assert [profile.label for profile in po.BUILT_IN] == [
        "ChoreBoy screen · 1366 × 768",
        "Small screen · 1024 × 600",
        "Full HD · 1920 × 1080",
    ]
    assert po.style_label("Fusion") == "Fusion · as on ChoreBoy"
    assert po.style_label("Windows") == "Windows"
    assert po.ordered_styles(["Windows", "Fusion", "macOS"]) == ("Fusion", "Windows", "macOS")


@pytest.mark.parity("R3-179")
def test_a_profile_is_held_to_its_ranges_and_a_built_in_name_cannot_be_reused() -> None:
    profile = po.clean_profile("  Old   laptop ", 100, 99999, "Courier", 500, 900)
    assert profile is not None
    assert (profile.name, profile.width, profile.height, profile.font_size, profile.scale) == (
        "Old laptop",
        po.MIN_WIDTH,
        po.MAX_HEIGHT,
        po.MAX_FONT,
        po.MAX_SCALE,
    )
    assert po.clean_profile("   ", 800, 600) is None
    assert po.name_is_built_in("small SCREEN")
    again = po.with_profile((profile,), po.clean_profile("old laptop", 1280, 720))
    assert [(item.name, item.width) for item in again] == [("old laptop", 1280)]


@pytest.mark.parity("R3-178", "R3-179")
def test_the_appearance_carries_the_profile_and_the_title() -> None:
    mine = po.clean_profile("Tablet", 1280, 800, "Courier", 14, 150)
    appearance = po.appearance_for("invoice.ui", po.PreviewChoices(style="Windows", screen="Tablet"), (mine,))
    assert appearance.style == "Windows" and appearance.scale == 1.5
    assert (appearance.screen_width, appearance.screen_height) == (1280, 800)
    assert (appearance.font_family, appearance.font_point_size) == ("Courier", 14.0)
    assert appearance.title == "Preview · invoice.ui · Windows style · Tablet"
    default = po.appearance_for("invoice.ui", po.PreviewChoices(), ())
    assert default.font_family is None and default.font_point_size is None and default.device_profile is None


@pytest.mark.parity("R3-179")
def test_choices_and_profiles_are_kept_per_user_outside_the_form(tmp_path: Path) -> None:
    store = PreviewOptionsStore(str(tmp_path))
    mine = po.clean_profile("Tablet", 1280, 800, "Courier", 14, 150)
    store.save(po.PreviewChoices(style="Windows", screen="Tablet"), (mine,))
    other = PreviewOptionsStore(str(tmp_path))
    choices, profiles = other.load()
    assert choices == po.PreviewChoices(style="Windows", screen="Tablet")
    assert profiles == (mine,)


def test_a_damaged_settings_block_is_the_default() -> None:
    assert preview_from_payload({"form_builder": {"preview": "oops"}}) == (po.PreviewChoices(), ())
    payload = payload_with_preview({}, po.PreviewChoices(), ())
    payload["form_builder"]["preview"]["profiles"] = [{"name": "Small screen", "width": 1, "height": 1}, {"name": 3}]
    assert preview_from_payload(payload)[1] == ()


@pytest.mark.parity("R3-181")
def test_the_index_finds_the_lines_of_a_widget_and_of_the_form() -> None:
    index = CodeIndex(_GENERATED)
    assert index.first_line("totalLabel") == 7
    assert index.lines_of("totalLabel") == (7, 8, 9, 14)
    # The form itself: the lines that start with it, not every line that passes it as a parent.
    assert index.lines_of("Till") == (2, 3, 4)
    assert index.name_on(8) == "totalLabel"
    assert index.name_on(4) == "Till"
    assert index.name_on(0) is None
    assert index.lines_of("missing") == () and index.first_line("missing") is None
