#!/usr/bin/env python3
"""Prepare Notion's Markdown & CSV export for md_to_latex_clipboard.py.

This is a *source adapter*, not a replacement LaTeX converter. It expects an
exported Markdown ZIP/directory or one Markdown file and uses only Python's
standard library. It deliberately preserves unsupported blocks as source text.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import unicodedata
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UUID = re.compile(r"\s+[0-9a-f]{32}$|\s+[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
IMAGE = re.compile(r"!\[(?P<alt>[^]\n]*)\]\((?P<target><[^>]+>|[^)\n]+)\)")
DISPLAY = re.compile(r"(?<!\$)\$\$(?!\$)(.*?)(?<!\$)\$\$(?!\$)", re.S)
TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEPARATOR = re.compile(r"^\s*\|\s*:?-{3,}:?\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
TABLE_CAPTION = re.compile(r"^\s*Table\s*(?:\d+\s*[.:\-]\s*|:\s*)(?P<caption>.+)$", re.I)
FENCES = re.compile(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$")
NUMERIC_LINK = re.compile(r"(?<!!)\[\[(?P<double_number>\d+)\]\]\((?P<double_target><[^>]+>|[^)\n]+)\)|(?<!!)\[(?P<single_number>\d+)\]\((?P<single_target><[^>]+>|[^)\n]+)\)")
CITATION_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_:.-]*$")


def canonical_doi(value: str) -> str | None:
    """Extract an identifier from DOI URLs and bare DOI strings."""
    value = unquote(value.strip()).strip("<>")
    url = urlsplit(value)
    if url.scheme.lower() in ("http", "https") and (url.hostname or "").lower() in {"doi.org", "dx.doi.org"}:
        value = url.path.strip("/")
    elif value.lower().startswith("doi:"):
        value = value[4:].strip()
    elif url.scheme or url.netloc:
        return None
    return value.casefold() if re.fullmatch(r"10\.\d{4,9}/[^\s?#]+", value, re.I) else None


def normalized_words(value: str) -> str:
    """Normalize titles for metadata matching; ignore braces and punctuation."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _bib_fields(body: str) -> dict[str, str]:
    """Read simple BibLaTeX fields, including braced values with nested braces."""
    result: dict[str, str] = {}
    cursor = 0
    pattern = re.compile(r"(?m)^\s*([A-Za-z][\w-]*)\s*=\s*")
    while match := pattern.search(body, cursor):
        name = match.group(1).lower()
        start = match.end()
        if start >= len(body):
            break
        if body[start] == "{":
            depth = 1
            end = start + 1
            while end < len(body) and depth:
                if body[end] == "{": depth += 1
                if body[end] == "}": depth -= 1
                end += 1
            value = body[start + 1:end - 1]
        elif body[start] == '"':
            end = body.find('"', start + 1)
            end = len(body) if end < 0 else end + 1
            value = body[start + 1:end - 1]
        else:
            end_match = re.search(r"[,\n]", body[start:])
            end = start + end_match.start() if end_match else len(body)
            value = body[start:end].strip()
        result[name] = value
        cursor = end
    return result


def read_bibliography(paths: list[Path]) -> list[dict[str, str]]:
    """Reuse keys from existing Zotero/Better BibTeX .bib files, not a custom map."""
    entries: list[dict[str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        headers = list(re.finditer(r"(?im)^\s*@(?!comment\b|preamble\b|string\b)[\w-]+\s*[{(]\s*([^,\s]+)\s*,", text))
        for i, match in enumerate(headers):
            fields = _bib_fields(text[match.end():headers[i + 1].start() if i + 1 < len(headers) else len(text)])
            fields["key"] = match.group(1).strip()
            if CITATION_KEY.fullmatch(fields["key"]):
                entries.append(fields)
    return entries


def citation_metadata(doi: str) -> dict[str, str] | None:
    """Retrieve published metadata from Crossref; no user API key required."""
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    request = Request(url, headers={"User-Agent": "NotionObsidianAdapter/0.2 (bibliographic metadata lookup)", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            data = json.load(response)["message"]
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError):
        return None
    title = data.get("title") or []
    author = data.get("author") or []
    date_parts = (data.get("issued") or data.get("published") or {}).get("date-parts") or []
    if not title or not author or not date_parts or not date_parts[0]:
        return None
    return {"title": title[0], "author": author[0].get("family", ""), "year": str(date_parts[0][0])}


def default_bbt_key(metadata: dict[str, str]) -> str | None:
    """Approximate BBT's default 'auth.lower + shorttitle(3,3) + year' pattern.

    This cannot reproduce custom formulas, pinned keys, or collision suffixes.
    """
    skip = {"a", "an", "the", "and", "of", "in", "on", "for", "to", "with", "or", "by", "from", "at", "as", "is", "are"}
    surname = re.sub(r"[^a-z0-9]", "", normalized_words(metadata.get("author", "")).replace(" ", ""))
    title_words = [word for word in normalized_words(metadata.get("title", "")).split() if word not in skip]
    year = metadata.get("year", "")
    if not surname or len(title_words) < 1 or not re.fullmatch(r"\d{4}", year):
        return None
    return surname + "".join(word.capitalize() for word in title_words[:3]) + year


class CitationResolver:
    """Resolve DOI-linked Notion citations, using actual BBT or .bib keys first."""

    def __init__(self, bib_files: list[Path] | None = None, *, use_zotero: bool = True,
                 metadata_lookup=None, rpc=None, allow_key_estimates: bool = False):
        self.entries = read_bibliography(bib_files or [])
        self.use_zotero = use_zotero
        self.allow_key_estimates = allow_key_estimates
        self.lookup = metadata_lookup or citation_metadata
        self.rpc = rpc or self._local_bbt_rpc
        self.cache: dict[str, tuple[str | None, str]] = {}

    @staticmethod
    def _local_bbt_rpc(method: str, params: list):
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
        request = Request("http://127.0.0.1:23119/better-bibtex/json-rpc", data=payload,
                          headers={"Content-Type": "application/json", "Accept": "application/json", "Zotero-Allowed-Request": "true"})
        try:
            with urlopen(request, timeout=1.5) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            return None
        return result.get("result") if isinstance(result, dict) and not result.get("error") else None

    @staticmethod
    def _metadata_matches(candidate: dict[str, str], metadata: dict[str, str]) -> bool:
        actual_title = normalized_words(candidate.get("title", ""))
        expected_title = normalized_words(metadata.get("title", ""))
        if actual_title != expected_title:
            # Publisher DOI metadata may include an edition/subtitle absent
            # from the Zotero record. Permit a long shared title prefix only.
            if len(min(actual_title, expected_title, key=len)) < 25 or not (actual_title.startswith(expected_title) or expected_title.startswith(actual_title)):
                return False
        author = normalized_words(candidate.get("author", ""))
        surname = normalized_words(metadata.get("author", ""))
        if surname and surname not in author.split() and surname not in author:
            return False
        # A DOI may describe an electronic publication dated later than the
        # version recorded in Zotero (e.g., Nielsen & Chuang: 2012 vs. 2010).
        # Only a unique title+author match is accepted by the caller. The year
        # is not evidence that these are different works.
        return True

    def _bib_match(self, doi: str, metadata: dict[str, str] | None) -> str | None:
        matches = [entry["key"] for entry in self.entries if canonical_doi(entry.get("doi", "")) == doi]
        if not matches and metadata:
            matches = [entry["key"] for entry in self.entries if self._metadata_matches(entry, metadata)]
        return matches[0] if len(set(matches)) == 1 else None

    def _zotero_match(self, doi: str, metadata: dict[str, str] | None) -> str | None:
        if not self.use_zotero:
            return None
        searches = [[["DOI", "is", doi]]]
        if metadata:
            # Zotero titles may omit subtitles/edition details present in
            # Crossref. Try the full title and then a shorter identifying prefix.
            title = metadata["title"].strip()
            searches.append([["title", "contains", title[:65]]])
            short_title = " ".join(title.split()[:3])
            if short_title and short_title != title[:65]:
                searches.append([["title", "contains", short_title]])
        for terms in searches:
            items = self.rpc("item.search", [terms])
            if not isinstance(items, list):
                continue
            matches = []
            for item in items:
                if not isinstance(item, dict): continue
                citekey = item.get("citekey", "")
                if not isinstance(citekey, str) or not CITATION_KEY.fullmatch(citekey): continue
                item_doi = canonical_doi(str(item.get("DOI", "")))
                if item_doi == doi or (metadata and self._metadata_matches({
                    "title": item.get("title", ""),
                    "author": " ".join(str(a.get("family", "")) for a in item.get("author", []) if isinstance(a, dict)),
                    "year": str(((item.get("issued") or {}).get("date-parts") or [[""]])[0][0]),
                }, metadata)):
                    matches.append(citekey)
            if len(set(matches)) == 1:
                return matches[0]
        return None

    def resolve(self, doi: str) -> tuple[str | None, str]:
        if doi in self.cache:
            return self.cache[doi]
        # The local Zotero + Better BibTeX service knows pinned and custom keys.
        result = self._zotero_match(doi, None)
        if result:
            self.cache[doi] = (result, "Zotero Better BibTeX")
            return self.cache[doi]
        # A Zotero .bib file may contain the DOI directly.
        result = self._bib_match(doi, None)
        if result:
            self.cache[doi] = (result, "Zotero bibliography")
            return self.cache[doi]
        metadata = self.lookup(doi)
        if metadata:
            result = self._zotero_match(doi, metadata)
            if result:
                self.cache[doi] = (result, "Zotero Better BibTeX")
                return self.cache[doi]
            result = self._bib_match(doi, metadata)
            if result:
                self.cache[doi] = (result, "Zotero bibliography")
                return self.cache[doi]
            if self.allow_key_estimates:
                result = default_bbt_key(metadata)
                if result:
                    self.cache[doi] = (result, "generated estimate")
                    return self.cache[doi]
        self.cache[doi] = (None, "unresolved")
        return self.cache[doi]


def convert_doi_citations(text: str, source: Path, resolver: CitationResolver,
                          warnings: list[str]) -> str:
    """Replace numbered DOI hyperlinks with [@key] when a key can be resolved."""
    seen: dict[str, str] = {}
    reported: set[str] = set()
    def replace(m: re.Match[str]) -> str:
        target = markdown_image_target(m.group("double_target") or m.group("single_target"))
        doi = canonical_doi(target)
        if doi is None:
            return m.group(0)
        number = m.group("double_number") or m.group("single_number")
        if number in seen and seen[number] != doi:
            warnings.append(f"{source.name}: citation [{number}] links to different DOIs")
            return m.group(0)
        seen[number] = doi
        key, resolution = resolver.resolve(doi)
        if not key:
            if doi not in reported:
                warnings.append(f"{source.name}: cannot resolve DOI {doi}; start Zotero with Better BibTeX or supply an exported --bib file")
                reported.add(doi)
            return m.group(0)
        if resolution == "generated estimate" and doi not in reported:
            warnings.append(f"{source.name}: guessed citation key {key} from DOI {doi}; verify it exists in your Zotero bibliography (custom/pinned keys may differ)")
            reported.add(doi)
        return f"[@{key}]"
    return NUMERIC_LINK.sub(replace, text)


def clean_title(stem: str) -> str:
    stem = unquote(stem)
    stem = UUID.sub("", stem).strip()
    return stem or "Untitled"


def safe_filename(name: str) -> str:
    # Obsidian note names are stored as files; remove problematic characters.
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name).strip(" .") or "Untitled"


def extract_zip(source: Path, dest: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            path = Path(item.filename)
            if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
                raise ValueError(f"Unsafe path in ZIP: {item.filename}")
            if item.file_size > 100_000_000:
                raise ValueError(f"Export item exceeds 100 MB limit: {item.filename}")
            # Reject Unix symbolic links to avoid extraction outside dest.
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symbolic link in ZIP: {item.filename}")
            out = dest / path
            if item.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as infile, out.open("wb") as outfile:
                    shutil.copyfileobj(infile, outfile)


def markdown_image_target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1]
    # Some Markdown exporters append a quoted title after the URL.
    raw = re.sub(r'\s+"[^\"]*"\s*$', "", raw)
    return unquote(raw)


def is_remote(target: str) -> bool:
    return bool(urlsplit(target).scheme) or target.startswith("//")


def build_pages(sources: list[Path]) -> dict[Path, str]:
    titles: dict[str, int] = {}
    result: dict[Path, str] = {}
    for source in sources:
        title = safe_filename(clean_title(source.stem))
        number = titles.get(title.casefold(), 0) + 1
        titles[title.casefold()] = number
        result[source] = title if number == 1 else f"{title} ({number})"
    return result


def linkify_pages(content: str, source: Path, pages: dict[Path, str]) -> str:
    """Convert local links to imported pages into Obsidian links (not web URLs)."""
    pattern = re.compile(r"(?<!!)\[(?P<name>[^\]]+)\]\((?P<target><[^>]+>|[^)\n]+)\)")
    def replace(m: re.Match[str]) -> str:
        target = markdown_image_target(m.group("target"))
        if is_remote(target):
            return m.group(0)
        path_str = target.split("#", 1)[0]
        if not path_str.lower().endswith(".md"):
            return m.group(0)
        candidate = (source.parent / path_str).resolve()
        if candidate not in pages:
            return m.group(0)
        display = m.group("name")
        return f"[[{pages[candidate]}|{display}]]"
    return pattern.sub(replace, content)


def count_images(text: str) -> int:
    return len(IMAGE.findall(text))


def normalize_page(text: str, title: str, latex_type: str, source: Path,
                   latex_parent: str | None,
                   figure_dir: Path, figure_placement: str,
                   media_map: dict[Path, str], pages: dict[Path, str],
                   warnings: list[str], resolver: CitationResolver | None = None) -> str:
    text = text.replace("\r\n", "\n").lstrip("\ufeff")
    # If the Notion export contains its page title as a heading, do not repeat it.
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.fullmatch(r"#\s+" + re.escape(title) + r"\s*", lines[0], re.I):
        lines.pop(0)
    text = "\n".join(lines).strip() + "\n"
    # Keep source code samples verbatim, without recognizing references or media inside.
    fenced: list[str] = []
    def hide_fence(m: re.Match[str]) -> str:
        fenced.append(m.group(0))
        return f"%%NOTION_FENCE_{len(fenced)-1}%%"
    text = FENCES.sub(hide_fence, text)
    # Shift headings only after code blocks have been protected.
    text = re.sub(r"(?m)^(#{1,5})(\s+)", lambda m: "#" * (len(m.group(1)) + 1) + m.group(2), text)

    # Number display equations in source order, preserving explicit existing tags.
    eq_count = 0
    def eq_replace(m: re.Match[str]) -> str:
        nonlocal eq_count
        eq_count += 1
        inner = m.group(1).strip()
        if not re.search(r"\\tag\s*\{", inner):
            inner += rf"\tag{{{eq_count}}}"
        return "$$\n" + inner + "\n$$"
    text = DISPLAY.sub(eq_replace, text)

    # Translate relative media paths and retain any image caption in Markdown alt.
    # Real Notion exports can duplicate the native caption in the next paragraph.
    figure_count = 0
    embedded_captions: dict[str, str] = {}
    def image_replace(m: re.Match[str]) -> str:
        nonlocal figure_count
        figure_count += 1
        alt = m.group("alt").strip()
        target = markdown_image_target(m.group("target"))
        if is_remote(target):
            warnings.append(f"{source.name}: external image not downloaded: {target}")
            return m.group(0)
        file_path = (source.parent / target).resolve()
        if not file_path.is_file():
            warnings.append(f"{source.name}: missing image attachment: {target}")
            return m.group(0)
        if file_path not in media_map:
            stem = safe_filename(file_path.stem)
            ext = file_path.suffix.lower()
            dest_name = stem + ext
            n = 2
            while (figure_dir / dest_name).exists() and not filecmp.cmp(file_path, figure_dir / dest_name, shallow=False):
                dest_name = f"{stem}_{n}{ext}"
                n += 1
            figure_dir.mkdir(parents=True, exist_ok=True)
            if not (figure_dir / dest_name).exists():
                shutil.copy2(file_path, figure_dir / dest_name)
            media_map[file_path] = dest_name
        filename = media_map[file_path]
        if not alt:
            warnings.append(f"{source.name}: figure {figure_count} has no exported caption")
        caption = alt.replace("|", r"\|").replace("\n", " ")
        place = f"|place:{figure_placement}" if figure_placement != "first" else ""
        embed = f"![[{filename}|center|fig:{figure_count}|desc:{caption}{place}]]"
        embedded_captions[embed] = alt
        return embed
    text = IMAGE.sub(image_replace, text)
    # Remove only an *identical* standalone caption directly following its image.
    # Other nearby prose, including captions written as distinct paragraphs, stays.
    if embedded_captions:
        cleaned_lines = []
        media_lines = text.splitlines()
        pos = 0
        while pos < len(media_lines):
            line = media_lines[pos]
            cleaned_lines.append(line)
            if line.strip() in embedded_captions:
                caption = embedded_captions[line.strip()]
                next_pos = pos + 1
                while next_pos < len(media_lines) and not media_lines[next_pos].strip():
                    next_pos += 1
                if caption and next_pos < len(media_lines) and media_lines[next_pos].strip() == caption:
                    pos = next_pos  # The image alt already contains the native caption.
            pos += 1
        text = "\n".join(cleaned_lines) + "\n"

    # Convert only explicitly captioned native Markdown tables into the
    # converter's table callouts; leave uncaptioned tables unchanged.
    lines = text.splitlines()
    out: list[str] = []
    table_count = 0
    idx = 0
    while idx < len(lines):
        if idx + 1 < len(lines) and TABLE_LINE.match(lines[idx]) and TABLE_SEPARATOR.match(lines[idx+1]):
            table_count += 1
            rows = [lines[idx], lines[idx + 1]]
            idx += 2
            while idx < len(lines) and TABLE_LINE.match(lines[idx]):
                rows.append(lines[idx]); idx += 1
            # Recognize ordinary natural-language caption directly above the table.
            caption_idx = len(out) - 1
            while caption_idx >= 0 and not out[caption_idx].strip():
                caption_idx -= 1
            caption_match = TABLE_CAPTION.match(out[caption_idx]) if caption_idx >= 0 else None
            if caption_match:
                caption = caption_match.group("caption")
                out = out[:caption_idx]
                out.append(f"> [!table: {table_count}] Table {table_count}. {caption}")
                if figure_placement == "here":
                    out.append("> <!-- latex: place:here -->")
                out.extend("> " + row for row in rows)
            else:
                warnings.append(f"{source.name}: table {table_count} has no preceding 'Table: caption' line")
                out.extend(rows)
            continue
        out.append(lines[idx]); idx += 1
    text = "\n".join(out)
    text = linkify_pages(text, source, pages)
    text = convert_doi_citations(text, source, resolver or CitationResolver(use_zotero=False, metadata_lookup=lambda doi: None), warnings)

    # Plain numbered references are optional. If explicitly written, make
    # them clickable without requiring Obsidian-specific LaTeX source syntax.
    def replace_prose_refs(part: str) -> str:
        def replace_ref(m: re.Match[str]) -> str:
            kind = m.group("kind").lower()
            num = int(m.group("number"))
            category = "eq" if kind.startswith("eq") else ("fig" if kind.startswith("fig") else "table")
            limit = {"eq": eq_count, "fig": figure_count, "table": table_count}[category]
            if not (1 <= num <= limit):
                warnings.append(f"{source.name}: {m.group(0)} has no matching numbered object")
                return m.group(0)
            return "$" + rf"\ref{{{category}:{num}}}" + "$"
        ref_re = re.compile(r"\b(?P<kind>Equation|Eq\.|Figure|Fig\.|Table)\s*\(?(?P<number>\d+)\)?", re.I)
        # Leave structural lines and generated embeds untouched.
        new_lines = []
        for line in part.splitlines():
            if line.lstrip().startswith(("> [!table", "> |", "![[", "#", "%%NOTION_FENCE")):
                new_lines.append(line)
            else:
                new_lines.append(ref_re.sub(replace_ref, line))
        return "\n".join(new_lines)
    # Keep reference replacement outside display math.
    components = DISPLAY.split(text)
    for i in range(0, len(components), 2):
        components[i] = replace_prose_refs(components[i])
    text = "".join((component if i % 2 == 0 else "$$" + component + "$$") for i, component in enumerate(components))
    for i, original in enumerate(fenced):
        text = text.replace(f"%%NOTION_FENCE_{i}%%", original)

    parent_line = f"Latex Parent: {latex_parent}\n" if latex_type == "Section" and latex_parent else ""
    header = f"---\nLatex Type: {latex_type}\n{parent_line}---\n"
    # For article demos, the first visible section comes from the Notion page title.
    if latex_type == "Article":
        return header + f"## {title}\n\n" + text.strip() + "\n"
    return header + text.strip() + "\n"


def process_export(input_path: Path, output: Path, latex_type: str, latex_parent: str | None,
                   figure_placement: str, warnings: list[str],
                   resolver: CitationResolver | None = None) -> list[Path]:
    input_path = input_path.resolve()
    output = output.resolve()
    if input_path.is_dir() and (output == input_path or input_path in output.parents):
        raise ValueError("Output folder must not be inside the input export directory")
    with tempfile.TemporaryDirectory(prefix="notion-obsidian-") as temporary:
        if input_path.suffix.lower() == ".zip":
            source_root = Path(temporary)
            extract_zip(input_path, source_root)
            sources = sorted(source_root.rglob("*.md"))
        elif input_path.is_dir():
            source_root = input_path
            sources = sorted(source_root.rglob("*.md"))
        elif input_path.suffix.lower() == ".md":
            source_root = input_path.parent
            sources = [input_path]
        else:
            raise ValueError("Input must be a Notion .zip, exported directory, or .md file")
        if not sources:
            raise ValueError("No Markdown pages found in the Notion export")
        pages = build_pages(sources)
        figure_dir = output / "Chapters" / "Figures"
        figure_dir.mkdir(parents=True, exist_ok=True)
        media_map: dict[Path, str] = {}
        written: list[Path] = []
        for source in sources:
            title = pages[source]
            body = source.read_text(encoding="utf-8-sig")
            rewritten = normalize_page(body, title, latex_type, source, latex_parent, figure_dir,
                                       figure_placement, media_map, pages, warnings, resolver)
            dest = output / f"{title}.md"
            dest.write_text(rewritten, encoding="utf-8")
            written.append(dest)
        return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a Notion Markdown export for the Obsidian-to-LaTeX converter")
    parser.add_argument("export", type=Path, help="Notion Markdown & CSV ZIP, extracted export folder, or a single Markdown file")
    parser.add_argument("--output", type=Path, default=Path("notion-converted"), help="Output Obsidian-vault folder")
    parser.add_argument("--latex-type", choices=("Article", "Chapter", "Section"), default="Article")
    parser.add_argument("--latex-parent", default=None, help="Parent chapter note when using --latex-type Section")
    parser.add_argument("--figure-placement", choices=("first", "here", "top", "near"), default="here")
    parser.add_argument("--strict", action="store_true", help="Exit with an error when content needs review")
    parser.add_argument("--bib", type=Path, action="append", help="Optional Zotero/Better BibTeX .bib file; can be repeated")
    parser.add_argument("--no-zotero", action="store_true", help="Do not query a running Zotero + Better BibTeX instance")
    parser.add_argument("--guess-citekeys", action="store_true", help="Opt in to UNVERIFIED citation-key estimates from DOI metadata (not guaranteed to match Zotero)")
    args = parser.parse_args()
    if args.latex_type == "Section" and not args.latex_parent:
        parser.error("--latex-parent is required for --latex-type Section")
    warnings: list[str] = []
    try:
        bib_files = args.bib or sorted({p.resolve() for folder in {Path.cwd(), Path(__file__).resolve().parent, args.export.resolve().parent}
                                         for p in folder.glob("*.bib") if p.is_file()})
        resolver = CitationResolver(bib_files, use_zotero=not args.no_zotero,
                                    allow_key_estimates=args.guess_citekeys)
        outputs = process_export(args.export, args.output, args.latex_type, args.latex_parent, args.figure_placement, warnings, resolver)
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    for output in outputs:
        print(output)
    for doi, (key, source) in sorted(resolver.cache.items()):
        if key:
            print(f"CITATION: {doi} -> [@{key}] ({source})", file=sys.stderr)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if args.strict and warnings:
        parser.exit(2, f"ERROR: {len(warnings)} conversion warning(s)\n")


if __name__ == "__main__":
    main()
