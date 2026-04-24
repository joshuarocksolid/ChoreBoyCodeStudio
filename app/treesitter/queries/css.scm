(comment) @comment
(string_value) @string
(color_value) @number
(integer_value) @number
(float_value) @number
(at_keyword) @keyword
(important) @keyword
(pseudo_class_selector (class_name) @keyword.control)
(pseudo_element_selector (tag_name) @keyword.control)
(feature_name) @property
(tag_name) @tag
(property_name) @property
(class_selector (class_name) @class.def)
(id_name) @variable
(function_name) @function.call
["{" "}" "(" ")" "[" "]"] @punctuation.bracket
[":" ";" "," "."] @punctuation.delimiter
