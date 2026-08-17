# Welcome and onboarding

With no project loaded, the center pane is a welcome screen: New/Open, recents, and a first-run checklist that stays reachable after a project auto-loads on a later launch.

Owns AT-73 (Runtime Center copy), AT-74, AT-76, AT-77, AT-80, smoke M2.

## Sub-features

- `welcome-visible` shows `#shell.welcome` when no project is open.
- `welcome-new-open` offers New Project and Open Project.
- `welcome-recents` lists recent projects and can filter them.
- `welcome-checklist` reaches Runtime Center, Getting Started, example project, Headless Notes.
- `welcome-onboarding-help` opens **Help → Runtime Onboarding...** even after a project is open.

## How to get to it (user POV)

- Launch with an empty recents list (disposable HOME).
- Click **New Project** or **Open Project** on the welcome pane.
- Use the onboarding card buttons, or **Help → Runtime Onboarding...**, **Help → Getting Started**.

## Driving it with control-cbcs

Preconditions:

- Fresh `--source` launch (empty recents).
- Doctor passed.
- `#shell.centerStack` is on the welcome page.

- **See welcome.** Run `control-cbcs ctl "$SID" exec -- "print(find('#shell.welcome') is not None)"`. Result is `True`. Shot `welcome-empty`.
- **Open Project control present.** Run `control-cbcs ctl "$SID" tree --max-depth 5` and confirm `#shell.welcome.openProjectBtn` and `#shell.welcome.newProjectBtn`.
- **Runtime Center from card.** Run `control-cbcs ctl "$SID" click 'text:Runtime Center'`. `#shell.runtimeCenterDialog` opens. Shot `welcome-runtime-center`. Close with `#shell.runtimeCenterDialog.closeButton`.
- **Getting Started.** Run `control-cbcs ctl "$SID" click 'text:Getting Started'`. `#shell.helpDialog` opens. Close with `#shell.helpDialog.closeBtn`.
- **Help menu onboarding.** Run `control-cbcs arm "$SID" shell.action.help.runtimeOnboarding` (modal — do not `trigger`). `#shell.runtimeOnboardingDialog` opens and is readable. Shot `welcome-onboarding`. Close with `reject()` via `ctl exec` or the dialog close button.
- **Proof.** Shots show the welcome identity (`ChoreBoy Code Studio`) and at least one help/runtime dialog. Welcome buttons remain after dialogs close.

## Gotchas

- Several onboarding buttons share `#shell.welcome.onboardingActionBtn`. Use `text:` for those.
- After **Help → Load Example Project** the welcome pane is replaced by the editor. Re-launch (or open no project) to return.
- On a non-isolated HOME, last-project restore skips welcome. That is why disposable HOME is required.
- Project Health on the card stays disabled until a project is open.
