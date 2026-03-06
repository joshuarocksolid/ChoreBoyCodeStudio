(comment) @comment
(string) @string
(raw_string) @string
(ansi_c_string) @string

(variable_name) @variable
(command_name) @function.call

(function_definition name: (word) @function.def)

["if" "then" "else" "elif" "fi" "for" "while" "do" "done"
 "case" "esac" "function" "in"] @keyword

["=" "|" "&" "||" "&&" "!" "<" ">" "<<" ">>"] @operator
