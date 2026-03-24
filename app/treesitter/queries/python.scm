(comment) @comment

(string) @string
(escape_sequence) @escape

(integer) @number
(float) @number
(true) @constant.builtin
(false) @constant.builtin
(none) @constant.builtin

(function_definition name: (identifier) @function.def)
(class_definition name: (identifier) @class.def)
(decorator (identifier) @decorator)
(decorator (attribute attribute: (identifier) @decorator))

(call function: (identifier) @function.call)
(call function: (attribute attribute: (identifier) @method.call))

(parameters (identifier) @parameter)
(default_parameter name: (identifier) @parameter)
(typed_parameter (identifier) @parameter)
(typed_default_parameter name: (identifier) @parameter)

(attribute attribute: (identifier) @property)

(assignment left: (identifier) @variable.def)

(type (identifier) @type)

["def" "class" "lambda"] @keyword

["return" "if" "elif" "else" "for" "while" "pass" "raise"
 "with" "try" "except" "finally" "yield" "global" "nonlocal"
 "del" "assert" "break" "continue"] @keyword.control

["import" "from" "as"] @keyword.import

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "//" "|" "&" "^" "~"
 "<" ">" "<=" ">=" "==" "!=" "+=" "-=" "*=" "/="
 "and" "or" "not" "in" "is"] @operator

(interpolation
 "{" @punctuation.delimiter
 "}" @punctuation.delimiter)

(identifier) @variable
