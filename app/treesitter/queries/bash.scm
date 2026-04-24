; --- Comments ---
(comment) @comment

; --- Strings & heredocs ---
(string) @string
(raw_string) @string
(ansi_c_string) @string
(translated_string) @string
(heredoc_body) @string
(heredoc_start) @string.special
(heredoc_end) @string.special

; Bare words on the right of a variable assignment read as string-like
; (e.g. `FOO=bar`, `URL=https://...`).
(variable_assignment (word) @string)

; Herestring payloads (`<<< "value"` or `<<< value`) are string-like.
(herestring_redirect (word) @string)

; --- Numbers & booleans ---
(number) @number

; `true` / `false` invoked as commands. The Python tree-sitter binding does
; not enforce `#any-of?` predicates, so we use `#match?` (which it does
; honor) with anchored regex alternations throughout this file.
((command_name (word) @boolean)
 (#match? @boolean "^(true|false)$"))

; --- Variables ---
; Order matters: more specific patterns come first so they win the
; equal-priority tie in `_append_capture_span` (the first span with a given
; range wins; later spans only override on a strictly higher priority).

; Special positional/status variables: $1, $?, $@, $#, $*, $$, $!, $-, $0
(special_variable_name) @variable.builtin

; Common Bash / POSIX builtin variables.
((variable_name) @variable.builtin
 (#match? @variable.builtin "^(BASH|BASHOPTS|BASHPID|BASH_ALIASES|BASH_ARGC|BASH_ARGV|BASH_ARGV0|BASH_CMDS|BASH_COMMAND|BASH_COMPAT|BASH_ENV|BASH_EXECUTION_STRING|BASH_LINENO|BASH_LOADABLES_PATH|BASH_REMATCH|BASH_SOURCE|BASH_SUBSHELL|BASH_VERSINFO|BASH_VERSION|BASH_XTRACEFD|CDPATH|COLUMNS|COMP_CWORD|COMP_KEY|COMP_LINE|COMP_POINT|COMP_TYPE|COMP_WORDBREAKS|COMP_WORDS|COMPREPLY|COPROC|DIRSTACK|EDITOR|EMACS|ENV|EPOCHREALTIME|EPOCHSECONDS|EUID|EXECIGNORE|FCEDIT|FIGNORE|FUNCNAME|FUNCNEST|GLOBIGNORE|GROUPS|HISTCMD|HISTCONTROL|HISTFILE|HISTFILESIZE|HISTIGNORE|HISTSIZE|HISTTIMEFORMAT|HOME|HOSTFILE|HOSTNAME|HOSTTYPE|IFS|IGNOREEOF|INPUTRC|INSIDE_EMACS|LANG|LC_ALL|LC_COLLATE|LC_CTYPE|LC_MESSAGES|LC_NUMERIC|LC_TIME|LINENO|LINES|MACHTYPE|MAIL|MAILCHECK|MAILPATH|MAPFILE|OLDPWD|OPTARG|OPTERR|OPTIND|OSTYPE|PATH|PIPESTATUS|POSIXLY_CORRECT|PPID|PROMPT_COMMAND|PROMPT_DIRTRIM|PS0|PS1|PS2|PS3|PS4|PWD|RANDOM|READLINE_ARGUMENT|READLINE_LINE|READLINE_MARK|READLINE_POINT|REPLY|SECONDS|SHELL|SHELLOPTS|SHLVL|SRANDOM|TERM|TIMEFORMAT|TMOUT|TMPDIR|UID|USER)$"))

; SCREAMING_SNAKE variable references read as constants.
((variable_name) @constant
 (#match? @constant "^[A-Z][A-Z0-9_]*$"))

; Generic variable fallback (lowest-precedence variable styling).
(variable_name) @variable

; --- Functions & commands ---
(function_definition name: (word) @function.def)

(command_name (word) @function.call)

; Builtin shell commands override the generic function.call coloring. The
; list below covers POSIX/Bash builtins (`help` output of `enable`).
((command_name (word) @function.builtin)
 (#match? @function.builtin "^(\\.|:|alias|bg|bind|break|builtin|caller|cd|command|compgen|complete|compopt|continue|coproc|declare|dirs|disown|echo|enable|eval|exec|exit|export|false|fc|fg|getopts|hash|help|history|jobs|kill|let|local|logout|mapfile|popd|printf|pushd|pwd|read|readarray|readonly|return|set|shift|shopt|source|suspend|test|time|times|trap|true|type|typeset|ulimit|umask|unalias|unset|wait)$"))

; --- Expansions ---
; ${VAR}
(expansion
  "${" @punctuation.special
  "}" @punctuation.special)

; $VAR (the leading dollar)
(simple_expansion "$" @punctuation.special)

; $( ... )
(command_substitution
  "$(" @punctuation.special
  ")" @punctuation.special)

; <( ... ) and >( ... )
(process_substitution
  ")" @punctuation.special)

; $(( ... )) and (( ... ))
(arithmetic_expansion
  "))" @punctuation.special)

; --- Redirections ---
(file_redirect (word) @string.special)
(file_descriptor) @number

; --- Test / arithmetic operators ---
(test_operator) @operator

(binary_expression operator: _ @operator)
(unary_expression operator: _ @operator)
(postfix_expression operator: _ @operator)

; --- Regex / extglob patterns ---
(regex) @string.regexp
(extglob_pattern) @string.regexp

; --- Case patterns ---
(case_item value: (word) @parameter)

; --- Keywords ---
["function"] @keyword

; Declarations: `declare`, `typeset`, `local`, `readonly`, `unset` read as
; ordinary keywords; `export` reads as an import-style keyword to mirror how
; other languages color module-level bindings.
["declare" "typeset" "local" "readonly" "unset" "unsetenv"] @keyword

["export"] @keyword.import

["if" "then" "else" "elif" "fi"
 "case" "esac" "in"
 "for" "select" "while" "until" "do" "done"] @keyword.control

; --- Brackets & delimiters ---
["(" ")" "{" "}" "[" "]" "[[" "]]" "((" "))"] @punctuation.bracket

[";" ";;" ";&" ";;&"] @punctuation.delimiter

; --- Operators ---
["=" "+="
 "==" "!=" "=~"
 "|" "|&" "&" "&&" "||" "!"
 "<" ">" "<<" ">>" "<<-" "<<<"
 "&>" "&>>" "<&" ">&" ">|"] @operator
