# Welcome and onboarding

With no project loaded, the center pane is a welcome screen with New/Open and recents. The first-run checklist is not on that landing pane. Open it from **Help → Runtime Onboarding...**.

Owns section-14 Runtime Center / onboarding ATs (the AT-73/AT-74 numbers in that section, not the completion ATs). AT-76 and AT-77 are run-failure flows, not this landing surface. Also AT-80, smoke M2.

<!-- dune-owners: platform.shell -->

## Sub-features

- `welcome-visible` shows `#shell.welcome` when no project is open.
- `welcome-new-open` offers New Project and Open Project.
- `welcome-recents` lists recent projects and can filter them.
- `welcome-checklist` is the onboarding card inside `#shell.runtimeOnboardingDialog`. `WelcomeWidget` starts with `set_onboarding_visible(False)`. The card appears only when Help forces it (`force_show_onboarding=True`).
- `welcome-onboarding-help` opens **Help → Runtime Onboarding...** even after a project is open.

## How to get to it (user POV)

- Launch with an empty recents list (disposable HOME).
- Click **New Project** or **Open Project** on the welcome pane.
- **Help → Runtime Onboarding...** shows the checklist card. **Help → Getting Started**. **Tools → Runtime Center...**.

## Driving it with control-cbcs

Preconditions:

- Fresh `--source` launch (empty recents).
- Doctor passed.
- `#shell.centerStack` is on the welcome page.

- **See welcome.** Run `control-cbcs ctl "$SID" exec -- "print(find('#shell.welcome') is not None)"`. Result is `True`. Shot `welcome-empty`.
- **Open Project control present.** Run `control-cbcs ctl "$SID" tree --max-depth 5` and confirm `#shell.welcome.openProjectBtn` and `#shell.welcome.newProjectBtn`.
- **Runtime Center.** `control-cbcs arm "$SID" shell.action.tools.runtimeCenter` (modal). `#shell.runtimeCenterDialog` opens. Shot `welcome-runtime-center`. Close with `d.reject()` via `ctl exec`. Do not click `text:Runtime Center` on the welcome pane. The card is hidden there.
- **Help menu onboarding.** `control-cbcs arm "$SID" shell.action.help.runtimeOnboarding`. `#shell.runtimeOnboardingDialog` opens. The onboarding card is visible, including **Runtime Center**. Shot `welcome-onboarding`. Close with `reject()`.
- **Proof.** Shots show the welcome identity (`ChoreBoy Code Studio`) and at least one help/runtime dialog. Welcome buttons remain after dialogs close.

## Gotchas

- Several onboarding buttons share `#shell.welcome.onboardingActionBtn`. Use `text:` for those, and only after the card is shown.
- After **Help → Load Example Project** the welcome pane is replaced by the editor. Re-launch (or open no project) to return.
- On a non-isolated HOME, last-project restore skips welcome. That is why disposable HOME is required.
- Project Health on the card stays disabled until a project is open.
- Chip click and `trigger` of Runtime Center / onboarding run `exec_()` and block the Qt bridge. Use `arm`. Close with `reject()` while the opener is still in `exec_()`.
