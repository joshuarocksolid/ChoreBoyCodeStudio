(comment) @comment
(string) @string
(raw_string) @string
(ansi_c_string) @string
(number) @number

(variable_name) @variable
(command_name) @function.call

(function_definition name: (word) @function.def)

["function"] @keyword

["if" "then" "else" "elif" "fi" "for" "while" "do" "done"
 "case" "esac" "in"] @keyword.control

["=" "|" "&" "||" "&&" "!" "<" ">" "<<" ">>"] @operator
