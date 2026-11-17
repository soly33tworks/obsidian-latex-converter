# Notion export to Obsidian Markdown

The optional [`notion_to_obsidian.py`](notion_to_obsidian.py) script converts a Notion **Markdown & CSV** export into Markdown suitable for the existing [`md_to_latex_clipboard.py`](md_to_latex_clipboard.py) converter. It does not require the Obsidian app, a separate launcher, a citation map, or the Notion API. The LaTeX converter and its behavior are unchanged.

## Export from Notion

1. Write a page using native Notion blocks: equation blocks for display mathematics, image blocks with native captions, and simple tables.
2. If referring to an object, write a numerical reference such as `Equation 1`, `Figure 1`, or `Table 1`. These references are matched within the exported page.
3. For bibliography citations, write a numerical citation such as `[1]` and make the number a **native hyperlink to the publication's DOI**, e.g. `https://doi.org/10.1017/CBO9780511976667`. The number is only a source-page placeholder; the LaTeX bibliography determines the final citation number.
4. For numbered tables, put a natural-language caption immediately above the table, such as `Table 1. Example pulse settings.`
5. Export the page using **Export → Markdown & CSV**, downloading the resulting ZIP. Notion's UUID-like ZIP filename is accepted without renaming or unpacking it.

## Run the adapter

Place the script wherever you prefer, then run it from the directory in which you want the output folder to appear:

```bash
python3 notion_to_obsidian.py 'your-original-notion-export-filename.zip' --strict
```

The script reads the ZIP directly and writes an output folder named `notion-converted/` by default. Override its location with `--output PATH`. A successful result contains Markdown note files and a `Chapters/Figures/` directory containing copied image assets. For a chapter or section note, use `--latex-type Chapter` or `--latex-type Section --latex-parent 'Parent Note'`; the default is `Article`.

## Zotero citations: no map file

The script looks up DOI-linked numbered citations in a **running Zotero instance with Better BibTeX**. If available, it obtains the actual Better BibTeX citation key rather than constructing one from the DOI's publication year.

Alternatively, pass a bibliography file exported from Zotero with Better BibTeX:

```bash
python3 notion_to_obsidian.py 'your-original-notion-export-filename.zip' --bib '/path/to/MAIN.bib' --strict
```

The script also checks for `.bib` files in its own directory, the current working directory, and the ZIP's directory if `--bib` is not given. The bibliography must contain the cited item, with its actual citation key. If a DOI cannot be matched reliably, the original link is retained and a warning is reported; with `--strict` the process exits with an error. Do not use `--guess-citekeys` if exact Zotero keys are required: that optional fallback produces **unverified estimates**.

For example, a native Notion link `[1]` pointing to the DOI for Nielsen and Chuang can become `[@nielsenQuantumComputationQuantum2010]` **when Zotero or the supplied bibliography actually has that key**. The adapter does not build bibliography entries; the downstream LaTeX project needs the matching `.bib` entry.

## Supported content and limits

The current adapter normalizes display equations, local images with exported captions, captioned simple Markdown tables, selected numerical equation/figure/table references, and relative links between exported Notion pages. It retains ordinary external links and unsupported text instead of trying to infer missing information.

The following do not have guaranteed conversion: Notion databases, synced or interactive blocks, complex column layouts, externally hosted images not included in the export, or numerical references whose target cannot be uniquely established. A caption absent from the Notion export cannot be recreated reliably. Check the converted Markdown and run strict mode before using it in a LaTeX document.

The adapter was exercised against a real single-page Notion Markdown export and includes 16 regression tests. The live Zotero integration needs to be verified with each user's own Zotero configuration; tests simulate the JSON-RPC response rather than requiring access to a personal library.

## Tests

With `notion_to_obsidian.py` and `test_notion_to_obsidian.py` in the same directory, run:

```bash
python3 -m unittest -v test_notion_to_obsidian.py
```

The scripts use the Python standard library. A live Zotero lookup requires Zotero and Better BibTeX running; using DOI metadata for title/author matching requires an internet connection when that fallback is needed.

## From Obsidian to LaTeX

Open the generated `notion-converted/` folder as an Obsidian vault if desired. The generated notes use the same tags, image embeds, table callouts and references as the existing Obsidian-to-LaTeX converter. See the main [README](README.md) and [Obsidian setup guide](OBSIDIAN_SETUP.md) for the separate LaTeX conversion workflow.
