from __future__ import annotations

import ctypes
import re
from pathlib import Path

from app.bootstrap.paths import resolve_app_root
from app.treesitter.language_specs import LANGUAGE_SPEC_BY_KEY, LANGUAGE_SPECS, TreeSitterLanguageSpec
from app.treesitter.loader import available_language_keys, initialize_tree_sitter_runtime, language_module, tree_sitter_module

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
        self._spec_by_extension: dict[str, TreeSitterLanguageSpec] = {}
        self._spec_by_key: dict[str, TreeSitterLanguageSpec] = dict(LANGUAGE_SPEC_BY_KEY)
        self._language_cache: dict[str, object] = {}
        self._query_cache: dict[str, str] = {}
        for spec in LANGUAGE_SPECS:
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

    def available_language_keys(self) -> tuple[str, ...]:
        status = initialize_tree_sitter_runtime(self._app_root)
        if not status.is_available:
            return ()
        return available_language_keys()

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
        grammar_module = language_module(key)
        if module is None or grammar_module is None:
            return None
        language_class = getattr(module, "Language", None)
        if language_class is None:
            return None
        language_fn = getattr(grammar_module, spec.language_callable_name, None)
        if not callable(language_fn):
            return None
        language_handle = language_fn()
        language_value = language_handle
        if isinstance(language_handle, ctypes.c_void_p):
            language_value = language_handle.value
        try:
            language = language_class(language_value, spec.language_name)
        except TypeError:
            language = language_class(language_value)
        self._language_cache[key] = language
        return language

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
            if self._looks_like_json(stripped):
                return ".json"
            if self._looks_like_markdown(stripped):
                return ".md"
            if self._looks_like_python(stripped):
                return ".py"
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
        first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
        if first_line.startswith(("#", "```", "~~~", "> ", "- ", "* ")):
            return True
        if re.match(r"^\d+[.)]\s+\S", first_line):
            return True
        if "[" in first_line and "](" in first_line:
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
