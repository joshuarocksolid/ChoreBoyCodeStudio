(comment) @comment

(string) @string

[
  (integer)
  (float)
] @number

(boolean) @json_literal

[
  (offset_date_time)
  (local_date_time)
  (local_date)
  (local_time)
] @number

(pair
  (bare_key) @json_key)

(pair
  (quoted_key) @json_key)

(pair
  (dotted_key
    (bare_key) @json_key))

(pair
  (dotted_key
    (quoted_key) @json_key))

(table
  (bare_key) @json_key)

(table
  (quoted_key) @json_key)

(table
  (dotted_key
    (bare_key) @json_key))

(table
  (dotted_key
    (quoted_key) @json_key))

[
  "."
  ","
] @punctuation.delimiter

"=" @operator

[
  "["
  "]"
  "[["
  "]]"
  "{"
  "}"
] @punctuation.bracket
