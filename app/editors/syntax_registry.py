"""Language highlighter registry and factory helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
import re
from typing import Any

from PySide2.QtGui import QTextDocument

from app.editors.syntax_engine import SyntaxPalette
from app.editors.syntax_json import JsonSyntaxHighlighter
from app.editors.syntax_markdown import MarkdownSyntaxHighlighter
from app.editors.syntax_python import PythonSyntaxHighlighter

HighlighterFactory = Callable[[QTextDocument, bool, Mapping[str, str] | None], object]
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


class SyntaxHighlighterRegistry:
    """Maps file extensions/language hints to highlighter factories."""

    def __init__(self) -> None:
        self._factories_by_extension: dict[str, HighlighterFactory] = {}

    def register(self, extensions: Iterable[str], factory: HighlighterFactory) -> None:
        for extension in extensions:
            key = extension.lower()
            if not key.startswith("."):
                key = f".{key}"
            self._factories_by_extension[key] = factory

    def create_for_path(
        self,
        *,
        file_path: str,
        document: QTextDocument,
        is_dark: bool,
        syntax_palette: Mapping[str, str] | None = None,
        sample_text: str = "",
    ) -> object | None:
        extension = Path(file_path).suffix.lower()
        factory = self._factories_by_extension.get(extension)
        if factory is None:
            sniffed_extension = self._sniff_extension(file_path=file_path, sample_text=sample_text)
            factory = self._factories_by_extension.get(sniffed_extension) if sniffed_extension else None
        if factory is None:
            return None
        return factory(document, is_dark, syntax_palette)

    @staticmethod
    def apply_theme(
        highlighter: object | None,
        *,
        is_dark: bool,
        syntax_palette: Mapping[str, str] | None = None,
    ) -> None:
        if highlighter is None:
            return
        if hasattr(highlighter, "set_theme_palette"):
            highlighter.set_theme_palette(syntax_palette, is_dark=is_dark)  # type: ignore[union-attr]
            return
        if hasattr(highlighter, "set_dark_mode"):
            highlighter.set_dark_mode(is_dark)  # type: ignore[union-attr]

    def _sniff_extension(self, *, file_path: str, sample_text: str) -> str | None:
        if sample_text:
            stripped = sample_text.lstrip()
            first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
            lower_first = first_line.lower()
            if first_line.startswith("#!") and "python" in lower_first:
                return ".py"
            if self._looks_like_json(stripped):
                return ".json"
            if self._looks_like_markdown(stripped):
                return ".md"
            if self._looks_like_python(stripped):
                return ".py"
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


def _python_factory(document: QTextDocument, is_dark: bool, syntax_palette: Mapping[str, str] | None) -> object:
    return PythonSyntaxHighlighter(document, is_dark=is_dark, syntax_palette=syntax_palette)


def _json_factory(document: QTextDocument, is_dark: bool, syntax_palette: Mapping[str, str] | None) -> object:
    return JsonSyntaxHighlighter(document, is_dark=is_dark, syntax_palette=syntax_palette)


def _markdown_factory(document: QTextDocument, is_dark: bool, syntax_palette: Mapping[str, str] | None) -> object:
    return MarkdownSyntaxHighlighter(document, is_dark=is_dark, syntax_palette=syntax_palette)


_DEFAULT_REGISTRY: SyntaxHighlighterRegistry | None = None


def default_syntax_highlighter_registry() -> SyntaxHighlighterRegistry:
    """Return lazily-initialized default syntax highlighter registry."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = SyntaxHighlighterRegistry()
        registry.register({".py", ".pyw", ".pyi"}, _python_factory)
        registry.register({".json", ".jsonc", ".json5"}, _json_factory)
        registry.register({".md", ".markdown", ".mdx", ".mkd"}, _markdown_factory)
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def syntax_palette_from_tokens(tokens: Any) -> SyntaxPalette:
    """Build syntax palette mapping from shell tokens."""
    return {
        "keyword": tokens.syntax_keyword,
        "builtin": tokens.syntax_builtin,
        "string": tokens.syntax_string,
        "comment": tokens.syntax_comment,
        "number": tokens.syntax_number,
        "function": tokens.syntax_function,
        "class": tokens.syntax_class,
        "decorator": tokens.syntax_decorator,
        "operator": tokens.syntax_operator,
        "punctuation": tokens.syntax_punctuation,
        "parameter": tokens.syntax_parameter,
        "json_key": tokens.syntax_json_key,
        "json_literal": tokens.syntax_json_literal,
        "markdown_heading": tokens.syntax_markdown_heading,
        "markdown_emphasis": tokens.syntax_markdown_emphasis,
        "markdown_code": tokens.syntax_markdown_code,
        "semantic_function": tokens.syntax_semantic_function,
        "semantic_method": tokens.syntax_semantic_method,
        "semantic_class": tokens.syntax_semantic_class,
        "semantic_parameter": tokens.syntax_semantic_parameter,
        "semantic_import": tokens.syntax_semantic_import,
        "semantic_variable": tokens.syntax_semantic_variable,
        "semantic_property": tokens.syntax_semantic_property,
        "semantic_constant": tokens.syntax_semantic_constant,
    }
