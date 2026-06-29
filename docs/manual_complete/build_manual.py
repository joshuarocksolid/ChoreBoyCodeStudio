#!/usr/bin/env python3
"""Build and validate the ChoreBoy Code Studio *Complete Edition* user manual.

This is the docs-as-code pipeline for the comprehensive manual. It renders a set
of Markdown chapters into a single searchable HTML document and a print-ready
PDF (Letter, full color) via headless Chrome.

It is intentionally self-contained (only Jinja2 + Chrome) so it runs on the
system Python without the FreeCAD AppRun runtime.

Supported Markdown subset (extended beyond the simple manual's renderer):

- ATX headings ``#``..``####`` with stable anchor IDs and a multi-level TOC
- Ordered and unordered lists (with single-level nested indentation)
- Fenced code blocks (```)
- Pipe tables (GitHub style)
- Callout blocks: lines beginning ``> [!TIP]``/``[!IMPORTANT]``/``[!NOTE]``/``[!LIMITATION]``
- Images ``![alt](path)`` rendered as ``<figure>`` with a caption
- Inline: ``code``, ``**bold**``, ``*italic*``, ``[text](url)`` (internal anchors + external)
- Horizontal rules ``---``

Commands::

    python3 docs/manual_complete/build_manual.py --check
    python3 docs/manual_complete/build_manual.py --html
    python3 docs/manual_complete/build_manual.py --pdf
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
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

VERSION = "1.0"
TITLE = "ChoreBoy Code Studio User Manual"
SUBTITLE = "Complete Edition"
PRODUCT_VERSION = "0.4.5"
HTML_FILENAME = f"ChoreBoy_Code_Studio_Complete_Manual_v{VERSION}.html"
PDF_FILENAME = f"ChoreBoy_Code_Studio_Complete_Manual_v{VERSION}.pdf"

MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
CALLOUT_RE = re.compile(r"^>\s*\[!(TIP|IMPORTANT|NOTE|LIMITATION)\]\s*(.*)$")

CALLOUT_LABELS = {
    "TIP": "Tip",
    "IMPORTANT": "Important",
    "NOTE": "Note",
    "LIMITATION": "Limitation",
}


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
    anchors: list[str]
    links: list[str]


_ANCHOR_COUNTS: dict[str, int] = {}


def slugify(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized or "section"


def unique_anchor(text: str) -> str:
    base = slugify(text)
    count = _ANCHOR_COUNTS.get(base, 0)
    _ANCHOR_COUNTS[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def _inline_markup(text: str, links_out: list[str] | None = None) -> str:
    # Protect inline code spans from other transforms.
    placeholders: list[str] = []

    def _stash_code(match: re.Match) -> str:
        placeholders.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(placeholders) - 1}\x00"

    working = INLINE_CODE_RE.sub(_stash_code, text)
    escaped = html.escape(working)

    def _link_sub(match: re.Match) -> str:
        label = match.group(1)
        target = match.group(2).strip()
        if links_out is not None:
            links_out.append(target)
        return f'<a href="{html.escape(target)}">{label}</a>'

    escaped = LINK_RE.sub(_link_sub, escaped)
    escaped = BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = ITALIC_RE.sub(r"<em>\1</em>", escaped)

    def _restore(match: re.Match) -> str:
        return placeholders[int(match.group(1))]

    escaped = re.sub(r"\x00(\d+)\x00", _restore, escaped)
    return escaped


def _is_table_separator(line: str) -> bool:
    stripped = line.strip().strip("|")
    if "-" not in stripped:
        return False
    cells = [c.strip() for c in stripped.split("|")]
    return all(re.fullmatch(r":?-{1,}:?", c or "") is not None for c in cells if c is not None) and bool(cells)


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def render_markdown(markdown_text: str) -> ChapterRender:
    lines = markdown_text.splitlines()
    out: list[str] = []
    toc: list[TocItem] = []
    image_targets: list[str] = []
    anchors: list[str] = []
    links: list[str] = []

    in_ul = False
    in_ol = False
    in_code = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body = " ".join(part.strip() for part in paragraph if part.strip())
            if body:
                out.append(f"<p>{_inline_markup(body, links)}</p>")
        paragraph = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    i = 0
    n = len(lines)
    while i < n:
        raw_line = lines[i]
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        # Fenced code blocks
        if stripped.startswith("```"):
            flush_paragraph()
            close_lists()
            if not in_code:
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            i += 1
            continue

        if in_code:
            out.append(html.escape(line))
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            close_lists()
            i += 1
            continue

        # Callout blocks
        callout_match = CALLOUT_RE.match(stripped)
        if callout_match:
            flush_paragraph()
            close_lists()
            kind = callout_match.group(1)
            first = callout_match.group(2).strip()
            body_lines: list[str] = [first] if first else []
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                cont = lines[i].strip()[1:].strip()
                body_lines.append(cont)
                i += 1
            body_html = _inline_markup(" ".join(b for b in body_lines if b), links)
            label = CALLOUT_LABELS[kind]
            out.append(
                f'<div class="callout callout-{kind.lower()}">'
                f'<span class="callout-label">{label}</span> {body_html}</div>'
            )
            continue

        # Headings
        heading_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            close_lists()
            level = len(heading_match.group(1))
            label = heading_match.group(2).strip()
            anchor = unique_anchor(label)
            anchors.append(anchor)
            out.append(f'<h{level} id="{anchor}">{_inline_markup(label, links)}</h{level}>')
            toc.append(TocItem(level=level, label=label, anchor=anchor))
            i += 1
            continue

        if stripped == "---":
            flush_paragraph()
            close_lists()
            out.append("<hr/>")
            i += 1
            continue

        # Tables (need a separator row directly after header)
        if "|" in stripped and (i + 1) < n and _is_table_separator(lines[i + 1]):
            flush_paragraph()
            close_lists()
            header = _split_row(stripped)
            i += 2  # skip header + separator
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            thead = "".join(f"<th>{_inline_markup(c, links)}</th>" for c in header)
            body_rows = []
            for row in rows:
                cells = "".join(f"<td>{_inline_markup(c, links)}</td>" for c in row)
                body_rows.append(f"<tr>{cells}</tr>")
            out.append(
                "<table><thead><tr>"
                + thead
                + "</tr></thead><tbody>"
                + "".join(body_rows)
                + "</tbody></table>"
            )
            continue

        # Images
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
                f'<figcaption class="image-caption">{_inline_markup(alt, links)}</figcaption>'
                "</figure>"
            )
            i += 1
            continue

        # Ordered list
        ordered_match = re.match(r"^(\s*)\d+\.\s+(.*)$", raw_line)
        if ordered_match:
            flush_paragraph()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline_markup(ordered_match.group(2), links)}</li>")
            i += 1
            continue

        # Unordered list
        bullet_match = re.match(r"^(\s*)[-*]\s+(.*)$", raw_line)
        if bullet_match:
            flush_paragraph()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            indent = len(bullet_match.group(1))
            cls = ' class="sub"' if indent >= 2 else ""
            out.append(f"<li{cls}>{_inline_markup(bullet_match.group(2), links)}</li>")
            i += 1
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    close_lists()
    if in_code:
        out.append("</code></pre>")
    return ChapterRender(
        path=Path("<memory>"),
        html="\n".join(out),
        toc=toc,
        image_targets=image_targets,
        anchors=anchors,
        links=links,
    )


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
        if shot.get("status") == "planned":
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


def validate_links(chapter_renders: list[ChapterRender]) -> list[str]:
    errors: list[str] = []
    all_anchors: set[str] = set()
    for chapter in chapter_renders:
        all_anchors.update(chapter.anchors)
    for chapter in chapter_renders:
        for link in chapter.links:
            if link.startswith("#"):
                anchor = link[1:]
                if anchor and anchor not in all_anchors:
                    errors.append(f"Broken internal anchor link '{link}' in {chapter.path.name}")
    return errors


def render_manual() -> tuple[str, list[str], list[ChapterRender]]:
    _ANCHOR_COUNTS.clear()
    chapter_paths = load_chapter_paths()
    if not chapter_paths:
        raise SystemExit(f"No chapter files found in {CHAPTERS_DIR}")

    chapter_renders: list[ChapterRender] = []
    all_toc: list[TocItem] = []
    all_images: list[str] = []
    for chapter_path in chapter_paths:
        rendered = render_markdown(read_text(chapter_path))
        rendered = ChapterRender(
            path=chapter_path,
            html=rendered.html,
            toc=rendered.toc,
            image_targets=rendered.image_targets,
            anchors=rendered.anchors,
            links=rendered.links,
        )
        chapter_renders.append(rendered)
        all_toc.extend(item for item in rendered.toc if item.level in (1, 2))
        all_images.extend(rendered.image_targets)

    css = read_text(TEMPLATES_DIR / "manual.css")
    template = Template(read_text(TEMPLATES_DIR / "manual.html"))
    rendered_html = template.render(
        title=TITLE,
        subtitle=SUBTITLE,
        version=VERSION,
        product_version=PRODUCT_VERSION,
        build_date=date.today().isoformat(),
        toc=all_toc,
        chapters=chapter_renders,
        css=css,
    )
    return rendered_html, all_images, chapter_renders


def write_html(html_text: str) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIST_DIR / HTML_FILENAME
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def build_pdf(html_path: Path) -> Path:
    import os
    import signal
    import time

    pdf_path = DIST_DIR / PDF_FILENAME
    if pdf_path.exists():
        pdf_path.unlink()
    url = html_path.resolve().as_uri()
    user_data_dir = tempfile.mkdtemp(prefix="cbcs_manual_chrome_")
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise SystemExit("No Chrome/Chromium binary found for PDF generation.")

    cmd = [
        chrome,
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
        "--no-pdf-header-footer",
        url,
    ]

    # Chrome headless often produces the PDF quickly but does not exit cleanly. Run it
    # detached, poll for a stable output file, then terminate the process group so we
    # never block on Chrome's slow shutdown.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 120
    last_size = -1
    stable_count = 0
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if pdf_path.exists():
                size = pdf_path.stat().st_size
                if size > 0 and size == last_size:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_count = 0
                last_size = size
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        shutil.rmtree(user_data_dir, ignore_errors=True)

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(f"PDF generation did not create a valid file: {pdf_path}")
    return pdf_path


def run_check(all_images: list[str], chapter_renders: list[ChapterRender]) -> None:
    errors: list[str] = []
    errors.extend(validate_shot_list())
    errors.extend(validate_images(all_images))
    errors.extend(validate_links(chapter_renders))
    if errors:
        print("Manual check failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"Manual check passed. ({len(chapter_renders)} chapters, {len(all_images)} image references)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ChoreBoy Code Studio Complete Edition manual.")
    parser.add_argument("--check", action="store_true", help="Run validation checks only.")
    parser.add_argument("--html", action="store_true", help="Render HTML output.")
    parser.add_argument("--pdf", action="store_true", help="Render HTML and PDF output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not (args.check or args.html or args.pdf):
        args.check = True

    rendered_html, all_images, chapter_renders = render_manual()

    if args.check:
        run_check(all_images, chapter_renders)
        if not (args.html or args.pdf):
            return 0

    html_path = write_html(rendered_html)
    print(f"Wrote HTML: {html_path}")

    if args.pdf:
        run_check(all_images, chapter_renders)
        pdf_path = build_pdf(html_path)
        print(f"Wrote PDF: {pdf_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
