# Navigation & Search

This chapter covers every way to find text and move quickly around your project: in-file
search, project-wide search, quick file opening, and symbol navigation.

## Find and replace in the current file

| Command | Shortcut | What it does |
| --- | --- | --- |
| Find | `Ctrl+F` | Open the find bar to search the active file. |
| Replace | `Ctrl+H` | Open find with a replace field. |
| Go To Line | `Ctrl+G` | Jump to a specific line number. |

The find bar supports case-sensitive, whole-word, and regular-expression matching, and
shows how many matches were found.

## Find in Files (project-wide search)

To search across every file in the project, choose **Edit > Find in Files**
(`Ctrl+Shift+F`). The sidebar switches to the **Search** view.

![Searching across the whole project with Find in Files](../screenshots/080_find_in_files.png)

- Type your query at the top. Toggle case-sensitive (**Aa**), whole-word (**W**), and
  regular-expression (**.\***) matching with the buttons beside it.
- Results are grouped by file, with a count per file and the total at the top
  (for example, "145 results in 5 files").
- Click any result to jump straight to that line in the editor.

> [!NOTE] Search runs in the background and can be cancelled, so even large projects stay
> responsive. Very long or pathological regular expressions are bounded to protect the
> editor.

## Quick Open (jump to any file)

Press `Ctrl+P` to open **Quick Open**, then type part of a file name. ChoreBoy Code
Studio fuzzy-matches your text against every file in the project.

![Quick Open matching files as you type](../screenshots/080_quick_open.png)

- The matched portions of each name are highlighted.
- Use the arrow keys to choose a result and press `Enter` to open it.
- A single click opens a preview; pressing `Enter` opens a permanent tab.

## Go to Symbol in File

Press `Ctrl+R` (**Tools > Go to Symbol in File**) to jump to a function or class within
the active file. Type to filter the list, then press `Enter`.

## The Outline panel

The **Outline** panel, below the Explorer, always lists the symbols in the file you are
editing. Click an entry to jump to it. The Outline updates as you edit.

## Go to Definition and Find References

These commands use real semantic analysis (see "Code intelligence"):

| Command | Shortcut | What it does |
| --- | --- | --- |
| Go To Definition | `F12` | Jump to where the symbol under the cursor is defined. |
| Find References | `Shift+F12` | List every place the symbol is used. |
| Show Hover Info | `Ctrl+Shift+I` | Show documentation for the symbol under the cursor. |
| Signature Help | `Ctrl+Shift+Space` | Show the call signature of the current function. |

## Where to go next

- Understand how definitions and references are resolved in "Code intelligence".
- Manage many open files efficiently with preview tabs (see "Editing files").
