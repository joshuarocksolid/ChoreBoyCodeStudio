from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass
from pathlib import Path

from app.bootstrap.paths import resolve_app_root
from app.treesitter.language_specs import (
    LANGUAGE_SPEC_BY_INJECTION_NAME,
    LANGUAGE_SPEC_BY_KEY,
    LANGUAGE_SPECS,
    TreeSitterLanguageSpec,
)
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


@dataclass(frozen=True)
class TreeSitterResolvedLanguage:
    language_key: str
    display_name: str
    language: object
    highlights_query_source: str
    locals_query_source: str = ""
    injections_query_source: str = ""


class TreeSitterLanguageRegistry:
    def __init__(self, *, app_root: Path | None = None) -> None:
        self._app_root = app_root if app_root is not None else resolve_app_root()
        self._query_dir = self._app_root / "app" / "treesitter" / "queries"
        self._spec_by_extension: dict[str, TreeSitterLanguageSpec] = {}
        self._spec_by_key: dict[str, TreeSitterLanguageSpec] = dict(LANGUAGE_SPEC_BY_KEY)
        self._language_cache: dict[str, object] = {}
        self._query_cache: dict[tuple[str, str], str] = {}
        for spec in LANGUAGE_SPECS:
            for extension in spec.extensions:
                self._spec_by_extension[extension] = spec

    def resolve_for_path(
        self,
        *,
        file_path: str,
        sample_text: str = "",
        override_language_key: str | None = None,
    ) -> TreeSitterResolvedLanguage | None:
        language_key = override_language_key or self._resolve_language_key(file_path=file_path, sample_text=sample_text)
        if language_key is None:
            return None
        return self.resolve_for_key(language_key)

    def resolve_for_key(self, language_key: str) -> TreeSitterResolvedLanguage | None:
        spec = self._spec_by_key.get(language_key)
        if spec is None:
            return None
        language = self._language_for_key(language_key)
        if language is None:
            return None
        return TreeSitterResolvedLanguage(
            language_key=language_key,
            display_name=spec.display_name,
            language=language,
            highlights_query_source=self._query_source_for_key(
                language_key=language_key,
                query_file=spec.highlights_query_file,
            ),
            locals_query_source=self._query_source_for_key(
                language_key=language_key,
                query_file=spec.locals_query_file,
            ),
            injections_query_source=self._query_source_for_key(
                language_key=language_key,
                query_file=spec.injections_query_file,
            ),
        )

    def resolve_for_injection_name(self, language_name: str) -> TreeSitterResolvedLanguage | None:
        normalized = language_name.strip().lower()
        if not normalized:
            return None
        spec = LANGUAGE_SPEC_BY_INJECTION_NAME.get(normalized)
        if spec is None:
            return None
        return self.resolve_for_key(spec.key)

    def available_language_keys(self) -> tuple[str, ...]:
        status = initialize_tree_sitter_runtime(self._app_root)
        if not status.is_available:
            return ()
        return available_language_keys()

    def available_language_modes(self) -> list[tuple[str, str]]:
        status = initialize_tree_sitter_runtime(self._app_root)
        if not status.is_available:
            return []
        modes: list[tuple[str, str]] = []
        available_keys = set(self.available_language_keys())
        for spec in LANGUAGE_SPECS:
            if spec.key not in available_keys:
                continue
            modes.append((spec.key, spec.display_name))
        return modes

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

    def _query_source_for_key(self, *, language_key: str, query_file: str) -> str:
        if not query_file:
            return ""
        cache_key = (language_key, query_file)
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            return cached
        query_path = self._query_dir / query_file
        if not query_path.exists():
            self._query_cache[cache_key] = ""
            return ""
        query_source = query_path.read_text(encoding="utf-8")
        self._query_cache[cache_key] = query_source
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
        if stripped.startswith("{"):
            remainder = stripped[1:].lstrip()
            return remainder.startswith(('"', "}"))
        if stripped.startswith("["):
            remainder = stripped[1:].lstrip()
            if not remainder:
                return False
            if remainder.startswith(("{", '"', "]")):
                return True
            return remainder[0] in "-0123456789tfn"
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
