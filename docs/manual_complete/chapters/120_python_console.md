# The Python Console (REPL)

The **Python Console** is an interactive Python prompt built into the editor. It is
perfect for quick experiments — trying an expression, checking a value, or exploring an
object — without creating or running a file.

## Where it is

The Python Console is one of the bottom panels. Select the **Python Console** tab. When
it starts, it prints a short banner and shows the familiar `>>>` prompt:

```text
ChoreBoy Python Console (runner process). Type exit() or Ctrl-D to close.
>>>
```

> [!NOTE] Like your programs, the Python Console runs in a **separate runner process**,
> not inside the editor. The objects you create live in that process, so nothing you do
> in the console can destabilize the editor.

## Using the console

Type Python at the prompt and press `Enter`:

```python
>>> tasks = ["Buy milk", "Write the manual"]
>>> len(tasks)
2
>>> tasks[0].upper()
'BUY MILK'
```

Multiline blocks work the way they do in a normal Python REPL — the prompt changes to
`...` while you are inside a block, and a blank line finishes it:

```python
>>> for t in tasks:
...     print("-", t)
...
- Buy milk
- Write the manual
```

## Output and history

- Everything the console prints appears in the transcript above the prompt.
- You can recall previous commands with the up/down arrow keys.
- Console history is remembered between sessions.

## Completion and help

The console offers completion and help based on the **live objects** in the running
session:

- Press `Ctrl+Space` (or type `.` after an object) to see attributes and methods that
  actually exist on your live objects.
- Selecting a callable shows its signature and documentation when available.

Because this introspection looks at real, live objects, it can discover attributes that
static analysis cannot — useful for exploring FreeCAD or Qt objects. The console labels
runtime-inspection results so you know they come from the live session.

> [!TIP] Completion in the **editor** (for files you are writing) is different: it uses
> static analysis and never executes your project code. See "Code intelligence". The
> console, by contrast, inspects the live session because that is where your objects
> exist.

## Restarting and interrupting

- **Run > Restart Python Console** (`` Ctrl+` ``) starts a fresh session, clearing all
  variables.
- Use **Stop** to interrupt a long-running console command.
- **Run > Clear Console** clears the transcript.

If the console session fails or times out, it reports the problem visibly and can be
restarted; it never takes the editor down with it.

## When to use the console vs a script

- Use the **console** for quick, throwaway experiments and to inspect values.
- Write a **file and run it** when you want something repeatable, or when your code is
  more than a few lines.

## Where to go next

- Get completion and navigation while writing files in "Code intelligence".
- Run and debug full programs in "Running code" and "Debugging".
