"""CB-10. Move an old Macro/Apps install into FreeCAD/Apps."""

from scenarios.model import Skip


def run(ctx) -> None:
    raise Skip(
        "CB-10 was NOT RUN in final-fc10. part1 step 7 plants "
        "~/.local/share/FreeCAD/Macro/Apps/crud_showcase at version 0.0.9 "
        "and Replace moves old_data.txt into /home/default/FreeCAD/Apps. "
        "That installer walk was not in the promoted final-fc10 drivers, "
        "and it shares the CB-8 crud_showcase installer."
    )
