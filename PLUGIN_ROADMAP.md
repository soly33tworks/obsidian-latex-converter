# Possible future directions

This document records how **Obsidian Markdown to LaTeX** could evolve if development resumes. It is **not an active development plan**, release schedule, feature commitment, or announcement of an Obsidian Community Plugin. The existing Python converter is a usable, standalone project and may remain unchanged.

The project's purpose is to support scientific writing in Obsidian while retaining editable LaTeX output and an independently managed LaTeX project. Any future work should build on that purpose rather than require the project to become a general-purpose Markdown engine or a complete LaTeX editor.

## Current state

The repository already provides:

- A Python 3.10+ command-line converter with an optional one-command Obsidian workflow through Shell Commands.
- Chapter, section, and article-body conversion, including supported equations, references, citations, figures, and tables.
- A separate Inkscape-based SVG-to-PDF helper.
- An implemented, tested Notion-export adapter that prepares Markdown for the main converter, rather than implementing a parallel LaTeX engine.
- Examples, a standalone LaTeX demonstration, setup guides, and regression suites.

Conversion currently prints a LaTeX body fragment to standard output. The documented Obsidian workflow copies it to the clipboard for use in a separate LaTeX document. This remains a valid long-term workflow, not merely a temporary workaround.

## Possible paths

The following are alternatives or independently useful extensions, **not stages that must be completed in order**.

### 1. Keep the current workflow

No significant code development is necessary for the project to remain useful. Documentation corrections, compatibility fixes, additional regression cases, or issue-specific patches could be made without expanding its responsibilities. Community forks may pursue different requirements independently.

### 2. Add a lightweight desktop Obsidian plugin

The most direct integration improvement would be an Obsidian command, such as **Convert current note to LaTeX**, with settings and feedback inside Obsidian. A TypeScript plugin could identify the active Markdown file, invoke the existing Python converter, display conversion warnings, and copy successful output to the clipboard.

This would reduce configuration work compared with Shell Commands while preserving the tested Python conversion behavior and the existing CLI. It would be a **desktop-only** integration because launching local subprocesses relies on Node.js desktop APIs. The Python converter need not be rewritten to make this interface possible.

A minimal plugin would not compile PDFs, generate bibliography files, export SVGs, manage a document template, or replace a LaTeX editor. These tasks are separate from invoking the converter.

#### Settings that would make sense

| Setting | Suggested behavior | Basis |
| --- | --- | --- |
| Python interpreter | Detect a suitable executable where possible, with a manual path override | Needed to run the existing engine |
| Converter script location | Configurable if installed separately; hidden if bundled reliably | Needed only for external-script packaging |
| Reference-index root | Current vault by default, optionally a chosen folder | Existing `--root` option |
| Strict conversion | Enabled by default; warnings prevent clipboard replacement | Existing `--strict` option |
| Figure directory | `Chapters/Figures` by default | Existing `--figure-dir` option |
| Figure placement | `first` by default | Existing `--figure-placement` option |
| Table placement | `auto` by default | Existing `--table-placement` option |
| Conversion feedback | Clear success, warning, and error notices, with optional details | Plugin interface behavior |

The active note would be detected automatically and would not need a persistent source-file setting. A file-export destination should only be exposed once direct `.tex` export exists. Bibliography styles, PDF compilers, and project templates should not become settings for a clipboard-only converter.

An implementation would need to handle unsaved editor changes, Unicode and spaced paths, interpreter discovery, subprocess failures, output encoding, and plugin disable/reload. Python should be invoked without shell interpolation. The clipboard should change only after a successful, nonempty conversion.

**Packaging is a separate decision.** A simple first prototype could point to a Python script already installed on the user's machine. A more self-contained plugin could distribute the script and manage an approved local copy for execution. Merely attaching a `.py` file to a GitHub release does not mean Obsidian's plugin installer will install it. Any packaging approach would need review against the Community Plugin distribution and security rules applicable at the time.

### 3. Export LaTeX files directly

A plugin or CLI extension could write generated `.tex` fragments to configurable locations instead of, or in addition to, copying them to the clipboard. This would be useful for documents with many sections and repeated conversions.

Possible safeguards include explicitly mapped output paths, a preview or confirmation before overwriting existing files, clear conversion warnings, and predictable treatment of filenames. The feature could leave the user free to compile with VS Code, LaTeX Workshop, a terminal, or another established build process.

This possibility does **not** require incorporating `pdflatex` or a PDF viewer into Obsidian.

### 4. Assemble a multi-note LaTeX document

A larger, distinct extension could let users select and order Obsidian notes, associate them with a LaTeX project, and generate the corresponding source fragments and master-file inclusions. It could support a thesis or paper without requiring users to paste every section manually.

Such a tool would need rules for document order, chapters versus article sections, templates, front matter, bibliography paths, figure assets, cross-note indexes, and updates to already generated files. It would also need to avoid silently overwriting custom LaTeX and distinguish user-authored files from generated content.

A useful intermediate implementation would **assemble source files only**, leaving compilation to a normal LaTeX toolchain. Automatic project creation or template management is a larger undertaking and is not necessary for the main converter.

### 5. Improve diagnostics, potentially including build feedback

The current converter can report conversion problems, such as unresolved references or unsupported conventions, but it cannot know whether an entire LaTeX project compiles correctly. A plugin could expose these existing warnings in a dedicated conversion report without taking responsibility for PDF generation.

LaTeX compilation errors belong to the **build process**. If integrated feedback were ever useful, an Obsidian extension could invoke or observe a configured external build tool and show its logs. Mapping compiler locations back to the source Markdown would require source-to-output location tracking, especially when headings, equations, tables, and figures change the generated line structure.

A complete Overleaf-like editing, compilation, PDF-preview, and error-navigation environment would be a substantial change in scope. It should not be assumed to follow from the existence of a Markdown-to-LaTeX converter.

### 6. Consider a native TypeScript conversion engine

Reimplementing the Python engine in TypeScript could remove the Python runtime dependency from a plugin and offer a path toward a broader range of Obsidian platforms. It would also require reimplementing and revalidating all established conversion conventions, including cross-note indexing, figure placement, table processing, and reference resolution.

For the current STEM audience, an installed Python interpreter is not an exceptional dependency. A TypeScript port would be justified mainly by a concrete portability or distribution requirement, not by a need to modernize working Python code. Mobile compatibility would still need separate testing and platform-aware design; changing languages alone would not guarantee it.

## Boundaries worth preserving

- **Maintain the standalone CLI.** A plugin, if created, should not make command-line conversion unavailable.
- **Keep conversion independent from compilation.** Generating `.tex` and building a PDF are different responsibilities unless a separate integration deliberately joins them.
- **Preserve established syntax and output.** Changes should be checked against the existing regression suite and representative multi-note documents.
- **Keep Notion support separate.** The adapter's role is to normalize an additional input format into the established Obsidian Markdown conventions, not to displace or duplicate the main converter.
- **Avoid unnecessary setup.** A new interface should make the existing workflow easier rather than require additional tools or configuration without a specific benefit.
- **Do not imply guaranteed compatibility.** Multi-platform support, templates, bibliography systems, and hardware-specific LaTeX tools would need explicit validation.

## If a Community Plugin were pursued

The [official sample plugin](https://github.com/obsidianmd/obsidian-sample-plugin) and [developer documentation](https://docs.obsidian.md/Plugins/Getting%20started/Build%20a%20plugin) would provide the starting point. A separate plugin repository could keep its release conventions independent of those of the Python converter, although it is not mandatory.

Before publication, any implementation would need an appropriate manifest, clear settings, suitable packaging of its executable dependencies, testing on supported desktop operating systems, and disclosure that it launches local Python processes. Obsidian's [manifest specification](https://docs.obsidian.md/Reference/Manifest), [submission requirements](https://docs.obsidian.md/community-directory/submission-requirements-for-plugins), and [developer policies](https://docs.obsidian.md/community-directory/developer-policies) should be checked when development actually occurs. Community-directory publication would also entail responsibilities for compatibility and security that are distinct from sharing an as-is script.

There is no commitment to pursue publication, to choose any particular architecture, or to resume development. This document exists to make the project's possible directions understandable without suggesting that they are scheduled work.
