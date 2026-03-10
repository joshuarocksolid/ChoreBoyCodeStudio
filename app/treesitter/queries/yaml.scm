(comment) @comment
(string_scalar) @string
(double_quote_scalar) @string
(single_quote_scalar) @string
(block_scalar) @string
(escape_sequence) @escape

(block_mapping_pair key: (flow_node) @json_key)
(flow_pair key: (flow_node) @json_key)

(integer_scalar) @number
(float_scalar) @number
(boolean_scalar) @json_literal
(null_scalar) @json_literal
(anchor_name) @variable
(alias_name) @variable
