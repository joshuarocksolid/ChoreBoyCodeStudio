(comment) @comment

(string) @string

(integer) @number
(float) @number
(true) @number
(false) @number
(none) @constant.builtin

(function_definition name: (identifier) @function.def)
(class_definition name: (identifier) @class.def)
(decorator (identifier) @decorator)
(decorator (attribute attribute: (identifier) @decorator))

(call function: (identifier) @function.call)
(call function: (attribute attribute: (identifier) @method.call))

(parameter (identifier) @parameter)
(default_parameter name: (identifier) @parameter)
(typed_parameter (identifier) @parameter)
(typed_default_parameter name: (identifier) @parameter)

(attribute attribute: (identifier) @property)

(assignment left: (identifier) @variable.def)

(type (identifier) @type)

["def" "class" "return" "if" "elif" "else" "for" "while"
 "import" "from" "as" "pass" "raise" "and" "or" "not" "in"
 "is" "with" "try" "except" "finally" "yield" "lambda"
 "global" "nonlocal" "del" "assert" "break" "continue"] @keyword

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "//" "|" "&" "^" "~"
 "<" ">" "<=" ">=" "==" "!=" "+=" "-=" "*=" "/="
 "and" "or" "not" "in" "is"] @operator

(identifier) @variable
