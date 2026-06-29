# Worked Tutorial: A Utility Script

This short tutorial builds a simple command-line-style utility from the **Utility Script**
template and shows how to pass arguments to it — even though ChoreBoy has no terminal.

## What you will build

A script that reads command-line arguments (`sys.argv`), does a small computation, and
prints the result to the Run Log. You will run it both without and with arguments.

## Step 1 — Create the project

1. **File > New Project from Template...**.
2. Choose **Utility Script (utility_script)**.
3. Name it (for example, `Adder`) and choose a location.

The generated `main.py` is a minimal, runnable script.

## Step 2 — Write the logic

Replace the body of `main.py` with something that uses arguments:

```python
import sys

def main():
    args = sys.argv[1:]
    numbers = [float(a) for a in args] if args else [1, 2, 3]
    print("Inputs:", numbers)
    print("Sum:", sum(numbers))

if __name__ == "__main__":
    main()
```

Save with `Ctrl+S`.

## Step 3 — Run with defaults

Press `F5` (**Run Active File**). With no arguments, the script uses its defaults and
prints the sum in the **Run Log**.

## Step 4 — Run with arguments (no terminal needed)

ChoreBoy has no terminal, but you can still pass `sys.argv`:

1. Choose **Run > Run With Arguments...** (`Ctrl+Shift+A`).
2. In **Arguments**, type `10 20 30`. Watch the live "Parsed argv" preview split it into
   three tokens.
3. Click **Run**. The Run Log now shows `Sum: 60.0`.

Try quoting too: type `--label "my numbers" 5 5`. The preview shows the quoted value kept
as one token. See "Running code" for the full arguments, working-directory, and
environment options, and how to save them as named configurations.

## Step 5 — Save a configuration

If you run with the same arguments often:

1. In the Run With Arguments dialog, click **Save as Configuration...** and name it.
2. Later, pick it from the status-bar run-target indicator and press `Shift+F5`.

The configuration is stored in `cbcs/project.json` under `run_configs` (see "File &
folder reference").

## Step 6 — Add a test

Extract the computation into a function and test it:

```python
def add_all(values):
    return sum(values)
```

Add `tests/test_adder.py` with `assert add_all([1, 2, 3]) == 6`, then run it from the
**Test Explorer**.

## Where to go next

- Pass complex inputs and environments in "Running code".
- Build something interactive in "Worked Tutorial: Build a Windowed (Qt) App".
