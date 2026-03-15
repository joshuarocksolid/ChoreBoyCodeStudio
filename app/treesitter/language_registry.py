from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass
from pathlib import Path

from app.bootstrap.paths import resolve_app_root
from app.treesitter.loader import initialize_tree_sitter_runtime, languages_library, tree_sitter_module


@dataclass(frozen=True)
class _LanguageSpec:
    key: str
    extensions: tuple[str, ...]
    query_file: str
    symbol_candidates: tuple[str, ...]
    language_name: str


_LANGUAGE_SPECS: tuple[_LanguageSpec, ...] = (
    _LanguageSpec(
        key="python",
        extensions=(".py", ".pyw", ".pyi", ".fcmacro"),
        query_file="python.scm",
        symbol_candidates=("tree_sitter_python",),
        language_name="python",
    ),
    _LanguageSpec(
        key="json",
        extensions=(".json", ".jsonc", ".json5"),
        query_file="json.scm",
        symbol_candidates=("tree_sitter_json",),
        language_name="json",
    ),
    _LanguageSpec(
        key="html",
        extensions=(".html", ".htm"),
        query_file="html.scm",
        symbol_candidates=("tree_sitter_html",),
        language_name="html",
    ),
    _LanguageSpec(
        key="xml",
        extensions=(".xml", ".jrxml", ".svg", ".xsl"),
        query_file="xml.scm",
        symbol_candidates=("tree_sitter_xml", "tree_sitter_html"),
        language_name="xml",
    ),
    _LanguageSpec(
        key="css",
        extensions=(".css",),
        query_file="css.scm",
        symbol_candidates=("tree_sitter_css",),
        language_name="css",
    ),
    _LanguageSpec(
        key="javascript",
        extensions=(".js", ".jsx", ".mjs"),
        query_file="javascript.scm",
        symbol_candidates=("tree_sitter_javascript",),
        language_name="javascript",
    ),
    _LanguageSpec(
        key="bash",
        extensions=(".sh", ".bash"),
        query_file="bash.scm",
        symbol_candidates=("tree_sitter_bash",),
        language_name="bash",
    ),
    _LanguageSpec(
        key="markdown",
        extensions=(".md", ".markdown", ".mdx", ".mkd"),
        query_file="markdown.scm",
        symbol_candidates=("tree_sitter_markdown",),
        language_name="markdown",
    ),
    _LanguageSpec(
        key="yaml",
        extensions=(".yaml", ".yml"),
        query_file="yaml.scm",
        symbol_candidates=("tree_sitter_yaml",),
        language_name="yaml",
    ),
    _LanguageSpec(
        key="sql",
        extensions=(".sql",),
        query_file="sql.scm",
        symbol_candidates=("tree_sitter_sql", "tree_sitter_sqlite"),
        language_name="sql",
    ),
)

_COMMON_MARKDOWN_BASENAMES = {
    "readme",
    "changelog",
    "changes",
    "history",
    "license",
    "copying",
    "contributing",
    "authors",
}
_COMMON_PYTHON_BASENAMES = {"sconstruct", "sconscript", "wscript", "conanfile"}
_PYTHON_LINE_PATTERN = re.compile(r"^\s*(?:def|class|async\s+def|from\s+\w+\s+import|import\s+\w+)\b")
_DEFAULT_REGISTRY: TreeSitterLanguageRegistry | None = None


class TreeSitterLanguageRegistry:
    def __init__(self, *, app_root: Path | None = None) -> None:
        self._app_root = app_root if app_root is not None else resolve_app_root()
        self._query_dir = self._app_root / "app" / "treesitter" / "queries"
        self._spec_by_extension: dict[str, _LanguageSpec] = {}
        self._spec_by_key: dict[str, _LanguageSpec] = {}
        self._language_cache: dict[str, object] = {}
        self._query_cache: dict[str, str] = {}
        for spec in _LANGUAGE_SPECS:
            self._spec_by_key[spec.key] = spec
            for extension in spec.extensions:
                self._spec_by_extension[extension] = spec

    def resolve_for_path(
        self,
        *,
        file_path: str,
        sample_text: str = "",
    ) -> tuple[str, object, str] | None:
        language_key = self._resolve_language_key(file_path=file_path, sample_text=sample_text)
        if language_key is None:
            return None
        language = self._language_for_key(language_key)
        if language is None:
            return None
        query_source = self._query_source_for_key(language_key)
        return (language_key, language, query_source)

    def _resolve_language_key(self, *, file_path: str, sample_text: str) -> str | None:
        extension = Path(file_path).suffix.lower()
        spec = self._spec_by_extension.get(extension)
        if spec is not None:
            return spec.key
        sniffed_extension = self._sniff_extension(file_path=file_path, sample_text=sample_text)
        if sniffed_extension is None:
            return None
        sniffed_spec = self._spec_by_extension.get(sniffed_extension)
        if sniffed_spec is None:
            return None
        return sniffed_spec.key

    def _language_for_key(self, key: str) -> object | None:
        cached = self._language_cache.get(key)
        if cached is not None:
            return cached
        spec = self._spec_by_key.get(key)
        if spec is None:
            return None
        status = initialize_tree_sitter_runtime(self._app_root)
        if not status.is_available:
            return None
        module = tree_sitter_module()
        library = languages_library()
        if module is None or library is None:
            return None
        language_class = getattr(module, "Language", None)
        if language_class is None:
            return None
        for symbol_name in spec.symbol_candidates:
            if not hasattr(library, symbol_name):
                continue
            language_fn = getattr(library, symbol_name)
            language_fn.restype = ctypes.c_void_p
            language_ptr = int(language_fn())
            if language_ptr == 0:
                continue
            language = language_class(language_ptr, spec.language_name)
            self._language_cache[key] = language
            return language
        return None

    def _query_source_for_key(self, key: str) -> str:
        cached = self._query_cache.get(key)
        if cached is not None:
            return cached
        spec = self._spec_by_key.get(key)
        if spec is None:
            return ""
        query_path = self._query_dir / spec.query_file
        if not query_path.exists():
            self._query_cache[key] = ""
            return ""
        query_source = query_path.read_text(encoding="utf-8")
        self._query_cache[key] = query_source
        return query_source

    def _sniff_extension(self, *, file_path: str, sample_text: str) -> str | None:
        stripped = sample_text.lstrip()
        if stripped:
            first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
            lower_first = first_line.lower()
            if first_line.startswith("#!") and "python" in lower_first:
                return ".py"
            if first_line.startswith("#!") and ("bash" in lower_first or "sh" in lower_first):
                return ".sh"
            if first_line.startswith("#!") and ("node" in lower_first or "deno" in lower_first):
                return ".js"
            if self._looks_like_python(stripped):
                return ".py"
            if self._looks_like_json(stripped):
                return ".json"
            if self._looks_like_markdown(stripped):
                return ".md"
            if self._looks_like_html(stripped):
                return ".html"
            if self._looks_like_xml(stripped):
                return ".xml"
        path_obj = Path(file_path)
        if path_obj.suffix:
            return None
        basename = path_obj.name.lower()
        if basename in _COMMON_MARKDOWN_BASENAMES:
            return ".md"
        if basename in _COMMON_PYTHON_BASENAMES:
            return ".py"
        return None

    @staticmethod
    def _looks_like_json(stripped: str) -> bool:
        if not stripped:
            return False
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if stripped.startswith('"') and ":" in stripped[:220]:
            return True
        return False

    @staticmethod
    def _looks_like_markdown(stripped: str) -> bool:
        if not stripped:
            return False
        lines = [line.rstrip() for line in stripped.splitlines()[:8] if line.strip()]
        if not lines:
            return False
        first_line = lines[0]
        if first_line.startswith(("```", "~~~", "> ", "- ", "* ")):
            return True
        if re.match(r"^\d+[.)]\s+\S", first_line):
            return True
        if "[" in first_line and "](" in first_line:
            return True
        heading_like = re.match(r"^#{1,6}\s+\S", first_line) is not None
        if not heading_like:
            return False
        for line in lines[1:]:
            if line.startswith(("```", "~~~", "> ", "- ", "* ")):
                return True
            if re.match(r"^\d+[.)]\s+\S", line):
                return True
            if "[" in line and "](" in line:
                return True
        return False

    @staticmethod
    def _looks_like_python(stripped: str) -> bool:
        if not stripped:
            return False
        for line in stripped.splitlines()[:10]:
            if _PYTHON_LINE_PATTERN.match(line):
                return True
        return False

    @staticmethod
    def _looks_like_html(stripped: str) -> bool:
        lowered = stripped.lower()
        return lowered.startswith("<!doctype html") or lowered.startswith("<html")

    @staticmethod
    def _looks_like_xml(stripped: str) -> bool:
        lowered = stripped.lower()
        return lowered.startswith("<?xml") or lowered.startswith("<jasperreport")


def default_tree_sitter_language_registry() -> TreeSitterLanguageRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = TreeSitterLanguageRegistry()
    return _DEFAULT_REGISTRY
