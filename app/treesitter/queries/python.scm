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
(decorator) @decorator
(decorator (identifier) @decorator)
(decorator (attribute attribute: (identifier) @decorator))

(call function: (identifier) @function.call)
(call function: (identifier) @constructor
  (#match? @constructor "^[A-Z]"))
(call function: (attribute attribute: (identifier) @method.call))

(import_statement
  name: (dotted_name (identifier) @import.module))
(import_statement
  name: (aliased_import alias: (identifier) @import.symbol))
(import_from_statement
  module_name: (dotted_name (identifier) @import.module))
(import_from_statement
  name: (dotted_name (identifier) @import.symbol))
(import_from_statement
  name: (aliased_import alias: (identifier) @import.symbol))

(parameters (identifier) @parameter)
(default_parameter name: (identifier) @parameter)
(typed_parameter (identifier) @parameter)
(typed_default_parameter name: (identifier) @parameter)

(attribute attribute: (identifier) @property)
(type (identifier) @type)
(type (attribute attribute: (identifier) @type))

((identifier) @constant
  (#match? @constant "^[A-Z][A-Z0-9_]*$"))

["def" "class" "lambda" "async"] @keyword

["return" "if" "elif" "else" "for" "while" "pass" "raise"
 "with" "try" "except" "finally" "yield" "global" "nonlocal"
 "del" "assert" "break" "continue" "await"] @keyword.control

["import" "from" "as"] @keyword.import

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "//" "|" "&" "^" "~"
 "<" ">" "<=" ">=" "==" "!=" "+=" "-=" "*=" "/="
 "and" "or" "not" "in" "is"] @operator

(interpolation
 "{" @punctuation.delimiter
 "}" @punctuation.delimiter)
