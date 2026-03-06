(comment) @comment
(string) @string
(template_string) @string
(regex) @string

(number) @number
(true) @number
(false) @number
(null) @constant.builtin

(identifier) @variable
(property_identifier) @property

(function_declaration name: (identifier) @function.def)
(class_declaration name: (identifier) @class.def)
(method_definition name: (property_identifier) @function.def)

(formal_parameters (identifier) @parameter)

(call_expression function: (identifier) @function.call)
(call_expression function: (member_expression property: (property_identifier) @method.call))

["function" "class" "return" "if" "else" "for" "while"
 "switch" "case" "break" "continue" "import" "export" "from"
 "as" "const" "let" "var" "new" "try" "catch" "finally"
 "throw" "await" "async"] @keyword

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "!" "==" "!=" "===" "!==" "<"
 ">" "<=" ">=" "&&" "||" "?" "??" "+=" "-=" "*=" "/=" "%="
 "=>" ] @operator
