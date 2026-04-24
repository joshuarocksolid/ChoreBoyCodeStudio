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

(function_declaration
  name: (identifier) @local.definition
  (#set! local.role "semantic_function")
  (#set! local.scope_lift "true"))

(class_declaration
  name: (identifier) @local.definition
  (#set! local.role "semantic_class"))

(method_definition
  name: (property_identifier) @local.definition
  (#set! local.role "semantic_function")
  (#set! local.scope_lift "true"))

(import_specifier
  name: (identifier) @local.definition
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_specifier
  alias: (identifier) @local.definition
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(namespace_import
  (identifier) @local.definition
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_clause
  (identifier) @local.definition
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(identifier) @local.reference
