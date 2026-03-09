#!/usr/bin/env python3
"""Build and validate ChoreBoy Code Studio user manual artifacts."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

try:
    from jinja2 import Template
except Exception as exc:  # pragma: no cover - dependency check path
    raise SystemExit(f"Jinja2 is required to build the manual: {exc}")

ROOT = Path(__file__).resolve().parent
CHAPTERS_DIR = ROOT / "chapters"
SCREENSHOTS_DIR = ROOT / "screenshots"
TEMPLATES_DIR = ROOT / "templates"
DIST_DIR = ROOT / "dist"

VERSION = "0.1"
TITLE = "ChoreBoy Code Studio User Manual"
SUBTITLE = "Hobbyist Edition"
HTML_FILENAME = f"ChoreBoy_Code_Studio_User_Manual_v{VERSION}.html"
PDF_FILENAME = f"ChoreBoy_Code_Studio_User_Manual_v{VERSION}.pdf"

MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


@dataclass(frozen=True)
class TocItem:
    level: int
    label: str
    anchor: str


@dataclass(frozen=True)
class ChapterRender:
    path: Path
    html: str
    toc: list[TocItem]
    image_targets: list[str]


def slugify(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized or "section"


def _inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = INLINE_CODE_RE.sub(lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    escaped = BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = ITALIC_RE.sub(r"<em>\1</em>", escaped)
    return escaped


def render_markdown(markdown_text: str) -> tuple[str, list[TocItem], list[str]]:
    lines = markdown_text.splitlines()
    out: list[str] = []
    toc: list[TocItem] = []
    image_targets: list[str] = []

    in_ul = False
    in_ol = False
    in_code = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body = " ".join(part.strip() for part in paragraph if part.strip())
            if body:
                out.append(f"<p>{_inline_markup(body)}</p>")
        paragraph = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_lists()
            if not in_code:
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            continue

        if in_code:
            out.append(html.escape(line))
            continue

        if not stripped:
            flush_paragraph()
            close_lists()
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            close_lists()
            level = len(heading_match.group(1))
            label = heading_match.group(2).strip()
            anchor = slugify(label)
            out.append(f'<h{level} id="{anchor}">{_inline_markup(label)}</h{level}>')
            toc.append(TocItem(level=level, label=label, anchor=anchor))
            continue

        if stripped == "---":
            flush_paragraph()
            close_lists()
            out.append("<hr/>")
            continue

        image_match = MARKDOWN_IMAGE_RE.match(stripped)
        if image_match:
            flush_paragraph()
            close_lists()
            alt = image_match.group(1).strip()
            target = image_match.group(2).strip()
            image_targets.append(target)
            out.append(
                "<figure>"
                f'<img src="{html.escape(target)}" alt="{html.escape(alt)}"/>'
                f'<p class="image-caption">{_inline_markup(alt)}</p>'
                "</figure>"
            )
            continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            flush_paragraph()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline_markup(ordered_match.group(1))}</li>")
            continue

        bullet_match = re.match(r"^-\s+(.*)$", stripped)
        if bullet_match:
            flush_paragraph()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_markup(bullet_match.group(1))}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    close_lists()
    if in_code:
        out.append("</code></pre>")
    return ("\n".join(out), toc, image_targets)


def load_chapter_paths() -> list[Path]:
    return sorted(CHAPTERS_DIR.glob("*.md"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_shot_list() -> list[str]:
    errors: list[str] = []
    shot_list_path = SCREENSHOTS_DIR / "shot_list.json"
    if not shot_list_path.exists():
        return [f"Missing screenshot manifest: {shot_list_path}"]
    payload = json.loads(read_text(shot_list_path))
    screenshots = payload.get("screenshots")
    if not isinstance(screenshots, list):
        return [f"Invalid screenshots array in {shot_list_path}"]
    for shot in screenshots:
        if not isinstance(shot, dict):
            errors.append("Invalid screenshot manifest entry: expected object")
            continue
        file_name = shot.get("file")
        if not isinstance(file_name, str) or not file_name.strip():
            errors.append(f"Invalid screenshot file entry: {shot}")
            continue
        file_path = SCREENSHOTS_DIR / file_name
        if not file_path.exists():
            errors.append(f"Screenshot declared but missing: {file_path}")
    return errors


def validate_images(referenced_targets: Iterable[str]) -> list[str]:
    errors: list[str] = []
    referenced_files: set[Path] = set()
    for target in referenced_targets:
        target_path = (CHAPTERS_DIR / target).resolve()
        referenced_files.add(target_path)
        if not target_path.exists():
            errors.append(f"Missing referenced image: {target}")

    png_files = set(p.resolve() for p in SCREENSHOTS_DIR.glob("*.png"))
    orphaned = sorted(png_files - referenced_files)
    for orphan in orphaned:
        errors.append(f"Orphaned screenshot (not referenced in chapters): {orphan.name}")
    return errors


def render_manual() -> tuple[str, list[str]]:
    chapter_paths = load_chapter_paths()
    if not chapter_paths:
        raise SystemExit(f"No chapter files found in {CHAPTERS_DIR}")

    chapter_renders: list[ChapterRender] = []
    all_toc: list[TocItem] = []
    all_images: list[str] = []
    for chapter_path in chapter_paths:
        chapter_html, chapter_toc, images = render_markdown(read_text(chapter_path))
        chapter_renders.append(ChapterRender(path=chapter_path, html=chapter_html, toc=chapter_toc, image_targets=images))
        all_toc.extend(item for item in chapter_toc if item.level == 1)
        all_images.extend(images)

    css = read_text(TEMPLATES_DIR / "manual.css")
    template = Template(read_text(TEMPLATES_DIR / "manual.html"))
    rendered_html = template.render(
        title=TITLE,
        subtitle=SUBTITLE,
        version=VERSION,
        build_date=date.today().isoformat(),
        toc=all_toc,
        chapters=chapter_renders,
        css=css,
    )
    return rendered_html, all_images


def write_html(html_text: str) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIST_DIR / HTML_FILENAME
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def build_pdf(html_path: Path) -> Path:
    pdf_path = DIST_DIR / PDF_FILENAME
    url = html_path.resolve().as_uri()
    user_data_dir = tempfile.mkdtemp(prefix="cbcs_manual_chrome_")
    try:
        cmd = [
            "google-chrome",
            "--headless",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--metrics-recording-only",
            f"--user-data-dir={user_data_dir}",
            f"--print-to-pdf={pdf_path}",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            url,
        ]
        try:
            completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if completed.returncode != 0 and not pdf_path.exists():
                raise SystemExit(
                    "Chrome PDF generation failed.\n"
                    f"Exit code: {completed.returncode}\n"
                    f"stderr:\n{completed.stderr.decode('utf-8', errors='replace')}"
                )
        except subprocess.TimeoutExpired:
            if not pdf_path.exists():
                raise SystemExit("Chrome PDF generation timed out and no PDF was produced.")
    finally:
        shutil.rmtree(user_data_dir, ignore_errors=True)
    if not pdf_path.exists():
        raise SystemExit(f"PDF generation did not create file: {pdf_path}")
    return pdf_path


def run_check(all_images: list[str]) -> None:
    errors = []
    errors.extend(validate_shot_list())
    errors.extend(validate_images(all_images))
    if errors:
        print("Manual check failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("Manual check passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ChoreBoy Code Studio manual.")
    parser.add_argument("--check", action="store_true", help="Run validation checks only.")
    parser.add_argument("--html", action="store_true", help="Render HTML output.")
    parser.add_argument("--pdf", action="store_true", help="Render HTML and PDF output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not (args.check or args.html or args.pdf):
        args.check = True

    rendered_html, all_images = render_manual()

    if args.check:
        run_check(all_images)
        if not (args.html or args.pdf):
            return 0

    html_path = write_html(rendered_html)
    print(f"Wrote HTML: {html_path}")

    if args.pdf:
        run_check(all_images)
        pdf_path = build_pdf(html_path)
        print(f"Wrote PDF: {pdf_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
