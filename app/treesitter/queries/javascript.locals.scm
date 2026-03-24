[
  (statement_block)
  (function_expression)
  (arrow_function)
  (function_declaration)
  (method_definition)
] @local.scope

(pattern/identifier) @local.definition

(variable_declarator
  name: (identifier) @local.definition)

(identifier) @local.reference
