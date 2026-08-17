# Project open and create

A user opens a folder with `cbcs/project.json`, imports a plain Python folder, creates a project from a template, or loads the bundled example. Invalid folders fail with an actionable message and leave the editor up.

Owns AT-03, AT-04, AT-17, AT-19, AT-20, AT-21, AT-24, AT-33.

## Sub-features

- `project-open-valid` opens a folder that already has `cbcs/project.json`.
- `project-import-folder` bootstraps metadata for a plain Python folder.
- `project-open-invalid` rejects a non-project folder without crashing.
- `project-new-template` creates `utility_script`, `qt_app`, or `headless_tool`.
- `project-recent` reopens a path from **File → Open Recent**.
- `project-example` copies and opens the CRUD showcase from Help.

## How to get to it (user POV)

- **File → Open Project...** (Ctrl+O) or welcome **Open Project**.
- **File → New Project...** (Ctrl+N) or **New Project from Template...**.
- **File → Open Recent**.
- **Help → Load Example Project...**.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Scratch destination under the disposable HOME or `/mnt/cbprobe/cbcs-verify/<run-id>/project`.
- For valid-open, seed a folder that already contains `cbcs/project.json` (copy `example_projects/crud_showcase` into the run tree).

Folder pickers are native dialogs. Prefer in-app Python that calls the same workflow the menu uses, then prove the visible result. If you must drive the picker, use `oskey` only after a fresh shot.

- **Seed example on the share.** From the Mac, rsync `example_projects/crud_showcase` to `debian:/home/joshua/shared-usb/cbcs-verify/<run-id>/project/crud`.
- **Open by path.** Run `control-cbcs ctl "$SID" exec --` with `win=find('#shell.mainWindow'); win._file_project_commands_workflow.open_project_by_path('/mnt/cbprobe/cbcs-verify/<run-id>/project/crud')` only if a user-visible Open dialog cannot be completed. Then assert the user-visible result below. Prefer triggering **File → Open Project** and typing the path when the dialog accepts it.
- **Tree and status.** `#shell.projectTree` has rows. `control-cbcs read "$SID" shell.projectStatusLabel` contains the project name.
- **Invalid folder.** Point Open Project at `/tmp` or an empty scratch dir. An error dialog appears; `#shell.mainWindow` is still visible. Shot `project-invalid`.
- **New from template.** `control-cbcs trigger "$SID" shell.action.file.newProjectFromTemplate`. Complete name + destination into the disposable tree. New folder contains `cbcs/project.json`. Project status updates.
- **Example.** `control-cbcs trigger "$SID" shell.action.help.loadExampleProject`. After the copy dialog, the showcase tree is visible.
- **Recent.** Stop, relaunch with the **same** HOME only if you are proving recents (not the default isolate-and-destroy path). **File → Open Recent** lists the path. Otherwise prove recents by reading `$HOME/choreboy_code_studio_state/recent_projects.json` before `stop`.
- **Proof.** Shot of the tree + `projectStatusLabel` text, and a guest read that `cbcs/project.json` exists.

## Gotchas

- Native file dialogs are not `#shell.*`. Shot first; `oskey` the path; do not guess coordinates.
- Opening another project replaces the current one. There is no Close Project command.
- `vendor/` is hidden in the tree by default.
- Proving recents requires leaving state in the disposable HOME and reading it before `stop` deletes the guest tree — copy `recent_projects.json` into the Mac artifact dir first.
