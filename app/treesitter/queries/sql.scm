(comment) @comment
(string) @string

(number) @number

(from_clause (identifier) @class.def)
(table_column name: (identifier) @property)

["SELECT" "FROM" "WHERE" "INSERT" "UPDATE" "DELETE" "CREATE" "DROP"
 "ALTER" "TABLE" "INTO" "VALUES" "SET" "JOIN" "LEFT" "RIGHT" "INNER"
 "OUTER" "ON" "AND" "OR" "NOT" "IN" "IS" "NULL" "AS" "ORDER" "BY"
 "GROUP" "HAVING" "LIMIT" "OFFSET" "DISTINCT" "UNION" "ALL" "EXISTS"
 "BETWEEN" "LIKE" "CASE" "WHEN" "THEN" "ELSE" "END" "BEGIN" "COMMIT"
 "ROLLBACK" "PRIMARY" "KEY" "FOREIGN" "REFERENCES" "INDEX" "VIEW"
 "select" "from" "where" "insert" "update" "delete" "create" "drop"
 "alter" "table" "into" "values" "set" "join" "left" "right" "inner"
 "outer" "on" "and" "or" "not" "in" "is" "null" "as" "order" "by"
 "group" "having" "limit" "offset" "distinct" "union" "all" "exists"
 "between" "like" "case" "when" "then" "else" "end" "begin" "commit"
 "rollback" "primary" "key" "foreign" "references" "index" "view"] @keyword

["=" "<" ">" "<=" ">=" "<>" "!=" "||" "+" "-" "*" "/"] @operator
["(" ")" "[" "]"] @punctuation.bracket
["," "." ";"] @punctuation.delimiter

(identifier) @variable
