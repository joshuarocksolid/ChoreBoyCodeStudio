(comment) @comment
(string) @string
(template_string) @string
(regex) @string
(escape_sequence) @escape

(number) @number
(true) @constant.builtin
(false) @constant.builtin
(null) @constant.builtin
(this) @variable.builtin
(super) @variable.builtin

(function_declaration name: (identifier) @function.def)
(class_declaration name: (identifier) @class.def)
(method_definition name: (property_identifier) @function.def)

(formal_parameters (identifier) @parameter)

(call_expression function: (identifier) @function.call)
(call_expression function: (member_expression property: (property_identifier) @method.call))

((identifier) @constructor
  (#match? @constructor "^[A-Z]"))

([
  (identifier)
  (shorthand_property_identifier)
  (shorthand_property_identifier_pattern)
] @constant
  (#match? @constant "^[A-Z_][A-Z\\d_]+$"))

["function" "class" "const" "let" "var" "new" "async"
 "static" "extends" "typeof" "instanceof" "void" "delete"
 "in" "of"] @keyword

["return" "if" "else" "for" "while" "switch" "case" "break"
 "continue" "try" "catch" "finally" "throw" "await" "do"
 "default" "yield" "debugger" "with"] @keyword.control

["import" "export" "from" "as"] @keyword.import

(template_substitution
 "${" @punctuation.delimiter
 "}" @punctuation.delimiter)

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "!" "==" "!=" "===" "!==" "<"
 ">" "<=" ">=" "&&" "||" "?" "??" "+=" "-=" "*=" "/=" "%="
 "=>" ] @operator

(property_identifier) @property
