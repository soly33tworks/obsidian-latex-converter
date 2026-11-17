#!/usr/bin/env python3
"""Batch-export SVG artwork to vector PDFs using the installed Inkscape CLI.

Default figure folder: Chapters/Figures, located relative to the Obsidian
vault/project root. The folder is located from the current working directory
or from the script location, including their parent directories. PDFs sit
beside the SVGs. This script does not modify the Markdown converter.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def svg_files(directory: Path, recursive: bool) -> list[Path]:
    paths = directory.rglob('*') if recursive else directory.iterdir()
    return sorted(p for p in paths if p.is_file() and p.suffix.lower() == '.svg')


def export_one(source: Path, inkscape: str, timeout: float = 120) -> None:
    destination = source.with_suffix('.pdf')
    with tempfile.NamedTemporaryFile(prefix='.svg-export-', suffix='.pdf', dir=destination.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    temporary.unlink()
    try:
        completed = subprocess.run(
            [inkscape, str(source), f'--export-filename={temporary}'],
            capture_output=True, text=True, check=False, timeout=timeout,
        )
        if completed.returncode != 0 or not temporary.exists() or temporary.stat().st_size < 20:
            details = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f'Inkscape export failed (exit {completed.returncode}): {details}')
        if not temporary.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError('Inkscape did not produce a valid PDF header')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


DEFAULT_FIGURE_DIRECTORY = Path('Chapters/Figures')


def default_figure_folder() -> Path:
    """Find the project's figure folder when launched by an Obsidian command."""
    if DEFAULT_FIGURE_DIRECTORY.is_absolute():
        return DEFAULT_FIGURE_DIRECTORY.expanduser().resolve()
    # If installed beside the SVGs, always process this exact figure folder,
    # regardless of the working directory used to launch the command.
    script_folder = Path(__file__).resolve().parent
    if script_folder.name == 'Figures' and script_folder.parent.name == 'Chapters':
        return script_folder
    for start in (Path.cwd(), script_folder):
        for root in (start, *start.parents):
            candidate = root / DEFAULT_FIGURE_DIRECTORY
            if candidate.is_dir():
                return candidate.resolve()
    raise FileNotFoundError(
        f'Cannot find {DEFAULT_FIGURE_DIRECTORY} from the working directory '
        'or the script location. Set DEFAULT_FIGURE_DIRECTORY near the top '
        'of this script to an absolute path if the script is outside your vault.'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Convert all SVG files in a figure folder to vector PDF (using Inkscape).')
    parser.add_argument('directory', nargs='?', default=None, help='Figure folder; defaults to Chapters/Figures in the Obsidian vault')
    parser.add_argument('--recursive', action='store_true', help='Include subdirectories')
    parser.add_argument('--force', action='store_true', help='Rebuild PDFs even if they are newer than the SVGs')
    parser.add_argument('--dry-run', action='store_true', help='Report planned work without invoking Inkscape')
    parser.add_argument('--inkscape', default='inkscape', help='Inkscape executable or full path')
    args = parser.parse_args(argv)

    try:
        directory = Path(args.directory).expanduser().resolve() if args.directory else default_figure_folder()
    except FileNotFoundError as exc:
        parser.error(str(exc))
    if not directory.is_dir():
        parser.error(f'not a directory: {directory}')
    paths = svg_files(directory, args.recursive)
    if not args.dry_run and not shutil.which(args.inkscape):
        parser.error(f'Inkscape executable not found: {args.inkscape}')

    converted = skipped = errors = 0
    for svg in paths:
        pdf = svg.with_suffix('.pdf')
        if pdf.exists() and not args.force and pdf.stat().st_mtime_ns >= svg.stat().st_mtime_ns:
            print(f'SKIP {svg.relative_to(directory)} (PDF up to date)')
            skipped += 1
            continue
        if args.dry_run:
            print(f'WOULD EXPORT {svg.relative_to(directory)} -> {pdf.relative_to(directory)}')
            continue
        try:
            export_one(svg, args.inkscape)
            print(f'EXPORTED {svg.relative_to(directory)} -> {pdf.relative_to(directory)}')
            converted += 1
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f'ERROR {svg.relative_to(directory)}: {exc}', file=sys.stderr)
            errors += 1
    print(f'{len(paths)} SVG(s): {converted} exported, {skipped} current, {errors} failed')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
