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
(parameters (list_splat_pattern (identifier) @parameter))
(parameters (dictionary_splat_pattern (identifier) @parameter))
(lambda_parameters (identifier) @parameter)
(lambda_parameters (list_splat_pattern (identifier) @parameter))
(lambda_parameters (dictionary_splat_pattern (identifier) @parameter))
(default_parameter name: (identifier) @parameter)
(typed_parameter (identifier) @parameter)
(typed_parameter (list_splat_pattern (identifier) @parameter))
(typed_parameter (dictionary_splat_pattern (identifier) @parameter))
(typed_default_parameter name: (identifier) @parameter)
(keyword_argument name: (identifier) @parameter)

(attribute attribute: (identifier) @property)
(type (identifier) @type)
(type (attribute attribute: (identifier) @type))

((identifier) @constant
  (#match? @constant "^[A-Z][A-Z0-9_]*$"))

((identifier) @variable.builtin
  (#match? @variable.builtin "^__[A-Za-z0-9_]+__$"))

((identifier) @variable.builtin
  (#match? @variable.builtin "^(BaseException|Exception|ArithmeticError|AssertionError|AttributeError|BlockingIOError|BrokenPipeError|BufferError|BytesWarning|ChildProcessError|ConnectionAbortedError|ConnectionError|ConnectionRefusedError|ConnectionResetError|DeprecationWarning|EOFError|EnvironmentError|FileExistsError|FileNotFoundError|FloatingPointError|FutureWarning|GeneratorExit|IOError|ImportError|ImportWarning|IndentationError|IndexError|InterruptedError|IsADirectoryError|KeyError|KeyboardInterrupt|LookupError|MemoryError|ModuleNotFoundError|NameError|NotADirectoryError|NotImplementedError|OSError|OverflowError|PendingDeprecationWarning|PermissionError|ProcessLookupError|RecursionError|ReferenceError|ResourceWarning|RuntimeError|RuntimeWarning|StopAsyncIteration|StopIteration|SyntaxError|SyntaxWarning|SystemError|SystemExit|TabError|TimeoutError|TypeError|UnboundLocalError|UnicodeDecodeError|UnicodeEncodeError|UnicodeError|UnicodeTranslateError|UnicodeWarning|UserWarning|ValueError|Warning|ZeroDivisionError|NotImplemented|Ellipsis)$"))

["def" "class" "lambda" "async"] @keyword

["return" "if" "elif" "else" "for" "while" "pass" "raise"
 "with" "try" "except" "finally" "yield" "global" "nonlocal"
 "del" "assert" "break" "continue" "await"
 "match" "case"] @keyword.control

["import" "from" "as"] @keyword.import

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "//" "|" "&" "^" "~" "@"
 "<" ">" "<=" ">=" "==" "!=" "<<" ">>"
 "+=" "-=" "*=" "/=" "%=" "**=" "//=" "@="
 "&=" "|=" "^=" "<<=" ">>=" ":="] @operator

["and" "or" "not" "in" "is"] @keyword.operator

(interpolation
 "{" @punctuation.delimiter
 "}" @punctuation.delimiter)

(interpolation (identifier) @variable)
(format_specifier) @string
(type_conversion) @decorator
