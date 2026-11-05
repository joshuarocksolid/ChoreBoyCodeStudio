# Rename and move a form

Rename or move a `.ui` file from the project tree. Code Studio moves the companions with it.

## What moves with the form

`ui_<name>.py` is regenerated for the new path. The window file is moved, and its import of the generated module is updated. Other Python files in the project that import the old module get the same edit.

A rename inside the same folder also updates open-form steps in other forms in that folder, and it regenerates those modules.

A hand-edited generated file is copied aside first, the same way a save does. See [Generated files](generated_files.md).

## Names Code Studio refuses

The new name has to be a Python name. It cannot start with `ui_` or `cbcs_`. It cannot be a Python keyword. The folder cannot already contain the `.ui` file, the generated module, or the window file.

The new path has to stay inside the project, and the file has to end in `.ui`.

If a file changes on disk before the rename finishes, the tree says a file changed before the rename could update it.

## A move to another folder

Open-form steps in the old folder still point at the old name. Those forms report that the form is not in this project's forms folder. Open each one and point the step at the new place. See FB120 in [Form problems](diagnostics.md).

A Python file that cannot be read or parsed is left as it is. Fix the import in that file yourself.

[Form builder manual](index.md)
