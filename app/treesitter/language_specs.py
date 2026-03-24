from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TreeSitterLanguageSpec:
    key: str
    extensions: tuple[str, ...]
    query_file: str
    language_name: str
    package_name: str
    language_callable_name: str = "language"
    included_by_default: bool = True


_LANGUAGE_SPECS: tuple[TreeSitterLanguageSpec, ...] = (
    TreeSitterLanguageSpec(
        key="python",
        extensions=(".py", ".pyw", ".pyi", ".fcmacro"),
        query_file="python.scm",
        language_name="python",
        package_name="tree_sitter_python",
    ),
    TreeSitterLanguageSpec(
        key="json",
        extensions=(".json", ".jsonc", ".json5"),
        query_file="json.scm",
        language_name="json",
        package_name="tree_sitter_json",
    ),
    TreeSitterLanguageSpec(
        key="html",
        extensions=(".html", ".htm"),
        query_file="html.scm",
        language_name="html",
        package_name="tree_sitter_html",
    ),
    TreeSitterLanguageSpec(
        key="xml",
        extensions=(".xml", ".jrxml", ".svg", ".xsl"),
        query_file="xml.scm",
        language_name="xml",
        package_name="tree_sitter_xml",
        language_callable_name="language_xml",
    ),
    TreeSitterLanguageSpec(
        key="css",
        extensions=(".css",),
        query_file="css.scm",
        language_name="css",
        package_name="tree_sitter_css",
    ),
    TreeSitterLanguageSpec(
        key="javascript",
        extensions=(".js", ".jsx", ".mjs"),
        query_file="javascript.scm",
        language_name="javascript",
        package_name="tree_sitter_javascript",
        included_by_default=False,
    ),
    TreeSitterLanguageSpec(
        key="bash",
        extensions=(".sh", ".bash"),
        query_file="bash.scm",
        language_name="bash",
        package_name="tree_sitter_bash",
    ),
    TreeSitterLanguageSpec(
        key="markdown",
        extensions=(".md", ".markdown", ".mdx", ".mkd"),
        query_file="markdown.scm",
        language_name="markdown",
        package_name="tree_sitter_markdown",
    ),
    TreeSitterLanguageSpec(
        key="yaml",
        extensions=(".yaml", ".yml"),
        query_file="yaml.scm",
        language_name="yaml",
        package_name="tree_sitter_yaml",
    ),
    TreeSitterLanguageSpec(
        key="sql",
        extensions=(".sql",),
        query_file="sql.scm",
        language_name="sql",
        package_name="tree_sitter_sql",
        included_by_default=False,
    ),
)

LANGUAGE_SPECS = _LANGUAGE_SPECS
LANGUAGE_SPEC_BY_KEY = {spec.key: spec for spec in _LANGUAGE_SPECS}
DEFAULT_LANGUAGE_KEYS = tuple(spec.key for spec in _LANGUAGE_SPECS if spec.included_by_default)
OPTIONAL_LANGUAGE_KEYS = tuple(spec.key for spec in _LANGUAGE_SPECS if not spec.included_by_default)
