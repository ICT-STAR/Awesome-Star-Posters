#!/usr/bin/env python3
"""Render poster PDF previews and rebuild the README preview gallery."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdf"
PPTX_DIR = ROOT / "pptx"
PREVIEW_DIR = ROOT / "previews"
README = ROOT / "README.md"
START_MARKER = "<!-- previews:start -->"
END_MARKER = "<!-- previews:end -->"
DEFAULT_DPI = 110


def repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def markdown_link(path: Path) -> str:
    return quote(repo_rel(path), safe="/")


def require_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise SystemExit(
            f"Missing required tool: {name}\n"
            "Install Poppler first. On macOS: brew install poppler"
        )
    return tool


def render_preview(pdftoppm: str, pdf_path: Path, dpi: int, force: bool) -> tuple[Path, bool]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    output = PREVIEW_DIR / f"{pdf_path.stem}.png"
    if output.exists() and not force:
        return output, False

    with tempfile.TemporaryDirectory(prefix="poster-preview-") as tmpdir:
        prefix = Path(tmpdir) / pdf_path.stem
        cmd = [
            pdftoppm,
            "-r",
            str(dpi),
            "-png",
            "-singlefile",
            str(pdf_path),
            str(prefix),
        ]
        subprocess.run(cmd, cwd=ROOT, check=True)
        rendered = prefix.with_suffix(".png")
        if not rendered.exists():
            raise RuntimeError(f"pdftoppm did not create {rendered}")
        os.replace(rendered, output)
    return output, True


def discover_pdfs() -> list[Path]:
    if not PDF_DIR.exists():
        raise SystemExit(f"Missing directory: {repo_rel(PDF_DIR)}")
    pdfs = sorted(PDF_DIR.glob("*.pdf"), key=lambda p: p.name.casefold())
    if not pdfs:
        raise SystemExit(f"No PDFs found in {repo_rel(PDF_DIR)}")
    return pdfs


def gallery_for(pdfs: list[Path]) -> str:
    blocks: list[str] = []
    for pdf_path in pdfs:
        stem = pdf_path.stem
        pptx_path = PPTX_DIR / f"{stem}.pptx"
        links = [f"[PDF]({markdown_link(pdf_path)})"]
        if pptx_path.exists():
            links.append(f"[PPTX]({markdown_link(pptx_path)})")

        preview_path = PREVIEW_DIR / f"{stem}.png"
        separator = " " + chr(0xB7) + " "
        blocks.append(
            f"### `{stem}`\n\n"
            f"{separator.join(links)}\n\n"
            f"<img src=\"{markdown_link(preview_path)}\" alt=\"{stem} preview\" width=\"100%\" />"
        )
    return "\n\n".join(blocks)


def split_readme(text: str) -> tuple[str, str, str, str]:
    marker_start = text.find(START_MARKER)
    marker_end = text.find(END_MARKER)
    if marker_start != -1 and marker_end != -1 and marker_end > marker_start:
        prefix = text[:marker_start]
        suffix = text[marker_end + len(END_MARKER) :]
        return prefix.rstrip(), START_MARKER, END_MARKER, suffix.lstrip("\n")

    match = re.search(r"^## .*Poster.*$", text, flags=re.MULTILINE)
    if not match:
        prefix = text.rstrip() + "\n\n## Poster Previews\n\n"
        return prefix.rstrip(), START_MARKER, END_MARKER, "\n---\n"

    section_start = match.start()
    section_text = text[section_start:]
    first_entry = re.search(r"^### ", section_text, flags=re.MULTILINE)
    if first_entry:
        prefix = text[: section_start + first_entry.start()]
    else:
        prefix = text.rstrip() + "\n\n"
    return prefix.rstrip(), START_MARKER, END_MARKER, "\n---\n"


def update_readme(pdfs: list[Path]) -> None:
    original = README.read_text(encoding="utf-8") if README.exists() else ""
    prefix, start, end, suffix = split_readme(original)
    gallery = gallery_for(pdfs)
    updated = f"{prefix}\n\n{start}\n{gallery}\n{end}\n{suffix}"
    README.write_text(updated.rstrip() + "\n", encoding="utf-8")


def remove_stale_previews(pdfs: list[Path]) -> list[Path]:
    keep = {f"{pdf.stem}.png" for pdf in pdfs}
    removed: list[Path] = []
    if not PREVIEW_DIR.exists():
        return removed
    for preview in PREVIEW_DIR.glob("*.png"):
        if preview.name not in keep:
            preview.unlink()
            removed.append(preview)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render first-page PNG previews from pdf/*.pdf and refresh README.md."
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="rendering DPI")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="skip PDFs whose preview PNG already exists",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove preview PNGs that no longer have a matching PDF",
    )
    args = parser.parse_args()

    pdftoppm = require_tool("pdftoppm")
    pdfs = discover_pdfs()

    for pdf_path in pdfs:
        preview, rendered = render_preview(pdftoppm, pdf_path, args.dpi, force=not args.missing_only)
        action = "rendered" if rendered else "skipped"
        print(f"{action} {repo_rel(preview)}")

    if args.clean:
        for preview in remove_stale_previews(pdfs):
            print(f"removed {repo_rel(preview)}")

    update_readme(pdfs)
    print(f"updated {repo_rel(README)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        raise SystemExit(exc.returncode)
