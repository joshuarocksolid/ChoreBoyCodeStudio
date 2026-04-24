(module) @local.scope
(function_definition) @local.scope
(class_definition) @local.scope
(lambda) @local.scope
(list_comprehension) @local.scope
(dictionary_comprehension) @local.scope
(set_comprehension) @local.scope
(generator_expression) @local.scope

(function_definition
  name: (identifier) @local.definition
  (#set! local.role "semantic_function"))

(class_definition
  name: (identifier) @local.definition
  (#set! local.role "semantic_class"))

(parameters
  (identifier) @local.definition
  (#set! local.role "semantic_parameter"))

(parameters
  (list_splat_pattern (identifier) @local.definition)
  (#set! local.role "semantic_parameter"))

(parameters
  (dictionary_splat_pattern (identifier) @local.definition)
  (#set! local.role "semantic_parameter"))

(default_parameter
  name: (identifier) @local.definition
  (#set! local.role "semantic_parameter"))

(typed_parameter
  (identifier) @local.definition
  (#set! local.role "semantic_parameter"))

(typed_default_parameter
  name: (identifier) @local.definition
  (#set! local.role "semantic_parameter"))

(import_statement
  name: (dotted_name (identifier) @local.definition)
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_statement
  name: (aliased_import
    name: (dotted_name (identifier))
    alias: (identifier) @local.definition)
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_from_statement
  module_name: (dotted_name (identifier) @local.definition)
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_from_statement
  name: (dotted_name (identifier) @local.definition)
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(import_from_statement
  name: (aliased_import
    name: (dotted_name (identifier))
    alias: (identifier) @local.definition)
  (#set! local.role "semantic_import")
  (#set! local.color_definition "true"))

(assignment
  left: (identifier) @local.definition
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(assignment
  left: (pattern_list (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(assignment
  left: (pattern_list (list_splat_pattern (identifier) @local.definition))
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(assignment
  left: (tuple_pattern (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(assignment
  left: (list_pattern (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_statement
  left: (identifier) @local.definition
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_statement
  left: (pattern_list (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_statement
  left: (tuple_pattern (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_in_clause
  left: (identifier) @local.definition
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_in_clause
  left: (pattern_list (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(for_in_clause
  left: (tuple_pattern (identifier) @local.definition)
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(with_item
  value: (as_pattern
    alias: (as_pattern_target (identifier) @local.definition))
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(except_clause
  value: (as_pattern
    alias: (as_pattern_target (identifier) @local.definition))
  (#set! local.role "semantic_variable")
  (#set! local.color_definition "true"))

(identifier) @local.reference
