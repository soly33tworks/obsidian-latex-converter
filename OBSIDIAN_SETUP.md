# Obsidian setup and optional writing tools

This guide describes how to run `md_to_latex_clipboard.py` **directly from Obsidian**, based on the author's working configuration. It is not necessary to copy the author's vault settings. The Python converter itself is independent of Obsidian plugins, Pandoc, Zotero, VS Code, and a particular LaTeX editor.

## One-click conversion inside Obsidian

**Required for this particular one-click workflow:** Obsidian desktop, Python 3.10+, and the community plugin [Shell Commands](https://github.com/Taitava/obsidian-shellcommands). Other ways of launching the script are equally valid.

1. Install and enable **Shell Commands** from **Settings → Community plugins**.
2. Put `md_to_latex_clipboard.py` somewhere on your computer. A convenient location is `<YOUR_VAULT>/.obsidian/scripts/md_to_latex_clipboard.py`. Create the `scripts` directory if needed.
3. In **Settings → Shell Commands**, add a new command. On Linux or macOS, enter:

   ```text
   python3 "/absolute/path/to/your/vault/.obsidian/scripts/md_to_latex_clipboard.py" {{file_path:absolute}} --root "/absolute/path/to/your/vault" --strict
   ```

   Replace the quoted script path with the path on your own computer. `{{file_path:absolute}}` is a **Shell Commands plugin variable**; leave it in place. The plugin substitutes the currently active note's path. On Windows, use an installed Python launcher (`python` or `py -3`) and a Windows-style script path.
4. In that command's settings, set **stdout → Clipboard** and **stderr → Notification**. Leave output buffered. Give the command an alias, for example `markdown2latex`, and make it available in the command palette. The source workflow has no mandatory confirmation dialog or hotkey.
5. Open a Markdown note and run the command from Obsidian's command palette (`Ctrl/Cmd+P`). Paste the generated LaTeX into the appropriate file in your LaTeX project. Normal use does not require a terminal.

The recommended command includes `--root` to index linked notes across the vault and `--strict` to suppress LaTeX output when conversion warnings occur. Replace the root path with your own vault directory. Both flags are optional: without `--root`, the converter indexes the active note's directory; without `--strict`, it can still emit output when warnings occur. The author's original command did not pass either flag.

The command **copies converted LaTeX to the clipboard**; it does not create a `.tex` file or invoke `pdflatex`.

## Note conventions used by the converter

```markdown
---
Latex Type: Section
Latex Parent: Theory
---
## 1) Qubit Dynamics

As shown in $\ref{eq:1}$, the rotation is unitary.

$$
U=\exp(-iHt/\hbar).\tag{1}
$$
```

`Latex Type: Chapter`, `Section`, and `Article` select the intended heading structure. Local `\tag{}` identifiers and `fig:` labels must be consistent, and other-note references require those notes to be discoverable through the project index. See the main [README](README.md) for the supported wikilink, figure, reference, and table syntax.

## Which plugins are actually needed?

| Component | Role | Required for this workflow? |
| --- | --- | --- |
| **Shell Commands** | Passes the active note path to Python; sends stdout to the clipboard | **Yes**, for the one-click Obsidian method described above |
| **Equation Citator** | Convenient equation/figure numbering and citations while writing in Obsidian | **Recommended for equation-heavy writing**; the converter supports its source formats but does not invoke the plugin |
| **Zotero + Better BibTeX** | Bibliography management, stable citation keys, and `.bib` export for LaTeX | **Recommended for citation-heavy writing**; bibliography export is separate from conversion |
| **Obsidian Pandoc** | Separate Markdown/Pandoc export features | **No**; the converter never runs Pandoc |
| **Pandoc Reference List** | Citation rendering and previews in Obsidian | **Optional**; not part of conversion |
| **Zotero Desktop Connector** | Zotero-related writing and citation integration | **Optional**; not part of conversion |
| **LaTeX Suite / Math Booster** | Editing conveniences; their plugin files may be present in a vault even when not enabled | **No** |
| **Inkscape** | External SVG → PDF vector conversion, when using `svg_to_pdf_batch.py` | **Optional**, needed only for that separate export script |

Equation references and bibliography management are standard needs in most STEM theses, but these particular plugins are recommendations rather than converter dependencies. Other installed or enabled Obsidian plugins, themes, CSS snippets, hotkeys, and visual preferences are **not** converter dependencies. Do not install a large plugin collection to reproduce this workflow.

### Optional Equation Citator compatibility

The author's Equation Citator settings use `eq:` for equation IDs, `fig:` for figure IDs, comma-delimited multiple citations, continuous ranges with `-`, and cross-file citations enabled. The converter supports the associated source syntax, including certain cross-note citation formats. These settings are useful to reproduce the same *authoring conventions*, but the converter does not need the plugin to be installed. Different plugin versions may render or insert citations differently.

### Pandoc, Zotero, and LaTeX bibliographies

Pandoc is **not required** to convert the notes. The converter changes citation markers like `[@someKey]` to `\cite{someKey}`. A LaTeX document must still have a bibliography system (BibTeX or `biblatex`/Biber, as appropriate) and access to the cited entries. Zotero with Better BibTeX is one way to maintain stable citation keys and export the matching `.bib` file. The Obsidian Pandoc plugin and Pandoc Reference List do not supply bibliography entries to the LaTeX compiler automatically.

Likewise, `pdflatex` and VS Code are just one way to compile the generated LaTeX. The converter emits LaTeX body content for your **own document class and preamble**. The [README](README.md#latex-integration) lists typical package requirements; the optional `demo/` contains a VS Code configuration, but it is not required by the converter.

## Figures: separate artwork preparation

When Markdown embeds an SVG, the converter references a same-stem PDF in the generated LaTeX. It never runs Inkscape. If your LaTeX engine does not support direct SVG inclusion, run the separate `svg_to_pdf_batch.py` helper (requires Inkscape) before compiling. Source artwork should be exported at its intended **physical print size**; only oversized artwork is downscaled by the converter's safety checks.

The example thesis-side figure directory is `Chapters/Figures`, relative to the **main LaTeX project**. Change it with `--figure-dir` if your project uses another structure. The figure directory is not relative to where the converter script is installed.

## What **not** to publish

**Do not upload your entire `.obsidian` folder or a compressed vault backup.** Obsidian's settings and plugin `data.json` files can contain machine-specific paths, personal accounts, citation-cache data, private reading/workspace history, and third-party plugin binaries. Likewise, `.pandoc/` can contain cached Zotero library data. None is needed for this repository.

Publish only the checked-in files distributed with this package. They include the converter, its tests, the optional SVG helper, and this sanitized setup guide. Anyone who wants to duplicate additional Obsidian preferences can configure their own plugins independently.

For a public demonstration, use the non-private `examples/demo_note.md` and follow [VISUAL_ASSETS.md](VISUAL_ASSETS.md) to record a genuine one-click GIF and source/output screenshots for the README.
