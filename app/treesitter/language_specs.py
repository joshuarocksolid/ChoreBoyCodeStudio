from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TreeSitterLanguageSpec:
    key: str
    display_name: str
    extensions: tuple[str, ...]
    highlights_query_file: str
    language_name: str
    package_name: str
    language_callable_name: str = "language"
    included_by_default: bool = True
    locals_query_file: str = ""
    injections_query_file: str = ""
    injection_aliases: tuple[str, ...] = ()


_LANGUAGE_SPECS: tuple[TreeSitterLanguageSpec, ...] = (
    TreeSitterLanguageSpec(
        key="python",
        display_name="Python",
        extensions=(".py", ".pyw", ".pyi", ".fcmacro"),
        highlights_query_file="python.scm",
        language_name="python",
        package_name="tree_sitter_python",
        locals_query_file="python.locals.scm",
        injection_aliases=("py",),
    ),
    TreeSitterLanguageSpec(
        key="json",
        display_name="JSON",
        extensions=(".json", ".jsonc", ".json5"),
        highlights_query_file="json.scm",
        language_name="json",
        package_name="tree_sitter_json",
    ),
    TreeSitterLanguageSpec(
        key="html",
        display_name="HTML",
        extensions=(".html", ".htm"),
        highlights_query_file="html.scm",
        language_name="html",
        package_name="tree_sitter_html",
        injections_query_file="html.injections.scm",
    ),
    TreeSitterLanguageSpec(
        key="xml",
        display_name="XML",
        extensions=(".xml", ".jrxml", ".svg", ".xsl", ".ui", ".qrc"),
        highlights_query_file="xml.scm",
        language_name="xml",
        package_name="tree_sitter_xml",
        language_callable_name="language_xml",
    ),
    TreeSitterLanguageSpec(
        key="css",
        display_name="CSS",
        extensions=(".css",),
        highlights_query_file="css.scm",
        language_name="css",
        package_name="tree_sitter_css",
    ),
    TreeSitterLanguageSpec(
        key="javascript",
        display_name="JavaScript",
        extensions=(".js", ".jsx", ".mjs"),
        highlights_query_file="javascript.scm",
        language_name="javascript",
        package_name="tree_sitter_javascript",
        locals_query_file="javascript.locals.scm",
        injection_aliases=("js", "node"),
    ),
    TreeSitterLanguageSpec(
        key="bash",
        display_name="Bash",
        extensions=(".sh", ".bash"),
        highlights_query_file="bash.scm",
        language_name="bash",
        package_name="tree_sitter_bash",
        injection_aliases=("sh", "shell"),
    ),
    TreeSitterLanguageSpec(
        key="markdown",
        display_name="Markdown",
        extensions=(".md", ".markdown", ".mdx", ".mkd"),
        highlights_query_file="markdown.scm",
        language_name="markdown",
        package_name="tree_sitter_markdown",
        injections_query_file="markdown.injections.scm",
        injection_aliases=("md",),
    ),
    TreeSitterLanguageSpec(
        key="yaml",
        display_name="YAML",
        extensions=(".yaml", ".yml"),
        highlights_query_file="yaml.scm",
        language_name="yaml",
        package_name="tree_sitter_yaml",
        injection_aliases=("yml",),
    ),
    TreeSitterLanguageSpec(
        key="toml",
        display_name="TOML",
        extensions=(".toml",),
        highlights_query_file="toml.scm",
        language_name="toml",
        package_name="tree_sitter_toml",
        injection_aliases=("tml",),
    ),
    TreeSitterLanguageSpec(
        key="sql",
        display_name="SQL",
        extensions=(".sql",),
        highlights_query_file="sql.scm",
        language_name="sql",
        package_name="tree_sitter_sql",
        included_by_default=False,
    ),
)

LANGUAGE_SPECS = _LANGUAGE_SPECS
LANGUAGE_SPEC_BY_KEY = {spec.key: spec for spec in _LANGUAGE_SPECS}
LANGUAGE_SPEC_BY_INJECTION_NAME = {
    name.lower(): spec
    for spec in _LANGUAGE_SPECS
    for name in (spec.key, spec.language_name, *spec.injection_aliases)
}
DEFAULT_LANGUAGE_KEYS = tuple(spec.key for spec in _LANGUAGE_SPECS if spec.included_by_default)
OPTIONAL_LANGUAGE_KEYS = tuple(spec.key for spec in _LANGUAGE_SPECS if not spec.included_by_default)
