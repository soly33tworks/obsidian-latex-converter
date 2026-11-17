"""Regression tests for md_to_latex_clipboard.py (standard library only)."""
from __future__ import annotations
from pathlib import Path
import contextlib
import importlib.util
import io
import re
import tempfile
import unittest

CONVERTER = Path(__file__).with_name('md_to_latex_clipboard.py')
spec = importlib.util.spec_from_file_location('thesis_converter', CONVERTER)
conv = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = conv
spec.loader.exec_module(conv)


class ConverterRegressions(unittest.TestCase):
    def test_appendix_forms(self):
        cases = {'Appendix Parameters': 'Parameters', 'Appendix: Parameters': 'Parameters',
                 'Appendix A: Parameters': 'Parameters', 'Appendix B) Pulse Shapes': 'Pulse Shapes',
                 'Appendix C. Calibration': 'Calibration', 'Appendix D - Details': 'Details',
                 'Appendix A Parameters': 'Parameters'}
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(conv.split_appendix_title(source), (True, expected))
        self.assertEqual(conv.split_appendix_title('Pulse Shapes'), (False, 'Pulse Shapes'))

    def test_table_callout_spaces_caption_reference(self):
        data = r'> [!table: 1] Table 1. **Calibration resources.** Resources for each method.' + '\n' + \
               '> | Method | $N_2$ |\n> | --- | ---: |\n> | RPE | $N_{2}$ |\n\nSee $\\ref{table:1}$.\n'
        # Ensure it has the intended one-backslash LaTeX source.
        data = data.replace(r'\\ref', r'\ref')
        state=conv.ConversionState()
        data=conv.convert_figure_and_equation_refs(data, 'sin')
        tex=conv.convert_tables(data,'sin',state)
        self.assertIn(r'\caption[Calibration resources]{\textbf{Calibration resources.} Resources for each method.}',tex)
        self.assertIn(r'\label{tab:sin_1}',tex)
        self.assertIn(r'$N_2$',tex)
        self.assertIn(r'$N_{2}$',tex)
        self.assertIn(r'\hyperref[tab:sin_1]{Table~\ref*{tab:sin_1}}',tex)

    def test_spaced_and_compact_table_syntax(self):
        for kind in ('table','long-table','longtable'):
            for tag in ('1', ' 1'):
                with self.subTest(kind=kind,tag=tag):
                    data=f'> [!{kind}:{tag}] **Title.** Explanation.\n>\n> | A | B |\n> | --- | --- |\n> | x | y |'
                    state=conv.ConversionState()
                    tex=conv.convert_tables(data,'sin',state)
                    self.assertIn(r'\label{tab:sin_1}',tex)
                    self.assertNotIn('[!',tex)
                    if kind == 'table':
                        self.assertIn(r'\begin{table}[H]',tex)
                    else:
                        self.assertIn(r'\begin{longtable}{ll}',tex)

    def test_escaped_percent_math_fonts_and_refs(self):
        self.assertEqual(conv.escape_latex_text(r'80\% and 20%'), r'80\% and 20\%')
        self.assertEqual(conv.convert_legacy_rm(r'\phi_{\rm err}'), r'\phi_{\mathrm{err}}')
        self.assertEqual(conv.convert_legacy_rm(r'\rm{GHz}'), r'\mathrm{GHz}')
        self.assertEqual(conv.convert_legacy_rm(r'\rm err'), r'\mathrm{err}')
        self.assertEqual(conv.convert_legacy_rm(r'\roman'), r'\roman')
        ref=conv.convert_figure_and_equation_refs(r'Eqs. $\ref{eq:A.7,A.8,A.9}$; $\ref{fig:B.1, }$', 'sin')
        self.assertIn(r'Eqs.~(\hyperref[eq:sin_A.7]{\ref*{eq:sin_A.7}--\ref*{eq:sin_A.9}})',ref)
        self.assertIn(r'\hyperref[fig:sin_B.1]{Fig.~\ref*{fig:sin_B.1}}',ref)

    def test_table_pipe_in_math_and_row_validation(self):
        self.assertEqual(conv.split_markdown_table_row(r'| $|a|$ | $x\|y$ | z |'), ['$|a|$', r'$x\|y$', 'z'])
        state=conv.ConversionState()
        stderr=io.StringIO()
        with contextlib.redirect_stderr(stderr):
            tex=conv.convert_tables('> [!table: 3] **Rows.**\n> | A | B |\n> | --- | --- |\n> | x | y | extra |', 'sin', state)
        self.assertIn('has 3 columns; expected 2',stderr.getvalue())
        self.assertIn('x & y & extra',tex)

    def test_chapter_with_tables_and_appendix_in_self_contained_fixture(self):
        """Representative chapter conversion without depending on private thesis notes."""
        note = r"""---
Latex Type: Chapter
---
## 1) Calibration protocol
The parameter $\phi_{\rm err}$ is discussed in $\ref{table:2}$.

> [!table: 1] Table 1. **Parameters.** Initial settings.
> | Name | Value |
> | --- | ---: |
> | Angle | 1 |

> [!table: 2] Table 2. **Resources.** Method counts.
> | Method | Circuits |
> | --- | ---: |
> | RPE | 5 |

## Appendix: Leakage-Sensitive Calibration
Additional diagnostics.
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'Single-Qubit Gate Calibration Through Angle Estimation.md'
            source.write_text(note, encoding='utf-8')
            state = conv.ConversionState()
            index = conv.build_project_index(root, source, state)
            tex = conv.convert_markdown_to_latex(note, source, index, state)
        self.assertEqual(state.warning_count, 0)
        self.assertIn(r'\chapter{Single-Qubit Gate Calibration Through Angle Estimation}', tex)
        self.assertIn(r'\label{ch:sin}', tex)
        self.assertEqual(tex.count(r'\begin{table}[H]'), 2)
        self.assertIn(r'\label{tab:sin_1}', tex)
        self.assertIn(r'\label{tab:sin_2}', tex)
        self.assertIn(r'\hyperref[tab:sin_2]{Table~\ref*{tab:sin_2}}', tex)
        self.assertIn(r'\phi_{\mathrm{err}}', tex)
        self.assertIn(r'\section{Leakage-Sensitive Calibration}', tex)
        self.assertNotIn('[!table:', tex)

    def test_section_range_cross_note_with_exact_obsidian_aliases(self):
        """The user-facing aliases are ignored; the linked headings determine both labels."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'Theory.md').write_text('---\nLatex Type: Chapter\n---\n', encoding='utf-8')
            target = root / 'Microwave Control of Transmons.md'
            target.write_text('---\nLatex Type: Section\nLatex Parent: Theory\n---\n'
                              '## 4) Coherent Leakage from Higher Transmon Levels\n'
                              '## 5) Drive-Induced Phase Error\n'
                              '## 6) Finite-Anharmonicity Correction to the Pulse-Area Relation\n', encoding='utf-8')
            first = '[[Microwave Control of Transmons#4) Coherent Leakage from Higher Transmon Levels|Sections 2.3.4]]'
            last = '[[Microwave Control of Transmons#6) Finite-Anharmonicity Correction to the Pulse-Area Relation|2.3.6]]'
            source = root / 'Calibration Results.md'
            source.write_text('---\nLatex Type: Chapter\n---\n' + first + '–' + last + '.\n', encoding='utf-8')
            state = conv.ConversionState()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                idx = conv.build_project_index(root, source, state)
                tex = conv.convert_markdown_to_latex(source.read_text(encoding='utf-8'), source, idx, state)
            self.assertEqual(state.warning_count, 0, err.getvalue())
            begin = 'subsec:thy_mis_coherent-leakage-from-higher-transmon-levels'
            end = 'subsec:thy_mis_finite-anharmonicity-correction-to-the-pulse-area-relation'
            self.assertIn(rf'\hyperref[{begin}]{{Sections~\ref*{{{begin}}}}}--\hyperref[{end}]{{\ref*{{{end}}}}}', tex)
            self.assertNotIn('2.3.4', tex)
            self.assertNotIn('2.3.6', tex)
            self.assertNotIn('[[', tex)

    def test_section_range_local_link_dash_variants(self):
        """Local heading links also form ranges for both hyphens and em dashes."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / 'Methods.md'
            first = '[[#1) Preparation|Sections 1.1]]'
            last = '[[#3) Readout|1.3]]'
            target.write_text('---\nLatex Type: Chapter\n---\n'
                              '## 1) Preparation\n## 2) Control\n## 3) Readout\n'
                              + first + ' - ' + last + '; ' + first + '—' + last + '.\n', encoding='utf-8')
            state = conv.ConversionState()
            idx = conv.build_project_index(root, target, state)
            tex = conv.convert_markdown_to_latex(target.read_text(encoding='utf-8'), target, idx, state)
            begin = 'sec:mes_preparation'
            end = 'sec:mes_readout'
            expected = rf'\hyperref[{begin}]{{Sections~\ref*{{{begin}}}}}--\hyperref[{end}]{{\ref*{{{end}}}}}'
            self.assertEqual(tex.count(expected), 2)
            self.assertEqual(state.warning_count, 0)

    def test_section_range_does_not_absorb_non_heading_wikilinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = root / 'Alpha.md'
            second = root / 'Beta.md'
            first.write_text('---\nLatex Type: Chapter\n---\n', encoding='utf-8')
            second.write_text('---\nLatex Type: Chapter\n---\n', encoding='utf-8')
            source = root / 'Methods.md'
            source.write_text('---\nLatex Type: Chapter\n---\n[[Alpha|first]]–[[Beta|second]]\n', encoding='utf-8')
            state = conv.ConversionState()
            index = conv.build_project_index(root, source, state)
            tex = conv.convert_markdown_to_latex(source.read_text(encoding='utf-8'), source, index, state)
            self.assertNotIn('Sections~', tex)
            self.assertIn('}–\\hyperref[', tex)
            self.assertEqual(state.warning_count, 0)

    def test_cross_note_equation_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Theory.md').write_text('---\nLatex Type: Chapter\n---\n')
            target = root / 'Microwave_Control_of_Transmons.md'
            target.write_text('---\nLatex Type: Section\nLatex Parent: Theory\n---\n\n'
                              '## 1) Pulse Control\n\n$$\nx=1 \\tag{2}\n$$\n\n$$\ny=2 \\tag{3}\n$$\n')
            source = root / 'Calibration Results.md'
            source.write_text('---\nLatex Type: Chapter\n---\n\n'
                              'Eq. (2) of [[Microwave_Control_of_Transmons]]; '
                              'Eqs. (2, 3) in [[Microwave_Control_of_Transmons#1) Pulse Control|details]]; '
                              'Eq. 3 of [[Microwave_Control_of_Transmons]].\n')
            state = conv.ConversionState()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                index = conv.build_project_index(root, source, state)
                tex = conv.convert_markdown_to_latex(source.read_text(), source, index, state)
            self.assertEqual(err.getvalue(), '')
            self.assertIn(r'\hyperref[eq:thy_mis_2]{Eq.~(\ref*{eq:thy_mis_2})}', tex)
            self.assertIn(r'Eqs.~(\hyperref[eq:thy_mis_2]{\ref*{eq:thy_mis_2}--\ref*{eq:thy_mis_3}})', tex)
            self.assertIn(r'\hyperref[eq:thy_mis_3]{Eq.~(\ref*{eq:thy_mis_3})}', tex)
            self.assertNotIn(' of \\hyperref[sec:thy_mis]', tex)
            self.assertNotIn('[[', tex)

    def test_cross_note_equation_warning_for_missing_tag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Theory.md').write_text('---\nLatex Type: Chapter\n---\n')
            (root / 'Transmon Qubit.md').write_text('---\nLatex Type: Section\nLatex Parent: Theory\n---\n\n$$z=0 \\tag{2}$$\n')
            source = root / 'Calibration Results.md'
            source.write_text('---\nLatex Type: Chapter\n---\n\nEq. (99) of [[Transmon Qubit]].\n')
            state = conv.ConversionState()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                index = conv.build_project_index(root, source, state)
                tex = conv.convert_markdown_to_latex(source.read_text(), source, index, state)
            self.assertIn("equation tag '99' not found in note 'Transmon Qubit'", err.getvalue())
            self.assertIn(r'\hyperref[eq:thy_trt_99]{Eq.~(\ref*{eq:thy_trt_99})}', tex)



    def test_local_equation_ranges_and_cross_note_alias(self):
        source = r"\ref{eq:3,4,5,6,8,10,11,12}"
        expected = (r"Eqs.~(\hyperref[eq:thy_nos_3]{\ref*{eq:thy_nos_3}--\ref*{eq:thy_nos_6}}, "
                    r"\hyperref[eq:thy_nos_8]{\ref*{eq:thy_nos_8}}, "
                    r"\hyperref[eq:thy_nos_10]{\ref*{eq:thy_nos_10}--\ref*{eq:thy_nos_12}})")
        self.assertEqual(conv.convert_figure_and_equation_refs(source, 'thy_nos'), expected)
        self.assertEqual(conv.convert_figure_and_equation_refs(r"\ref{eq:3-6, 8, 10-12}", 'thy_nos'), expected)
        self.assertEqual(conv.convert_figure_and_equation_refs(r"\ref{eq:3~6,8,10~12}", 'thy_nos'), expected)

    def test_nonconsecutive_figure_table_references_and_panel_suffix(self):
        converted = conv.convert_figure_and_equation_refs(
            r"\ref{fig:1,2,4} and \ref{table:1,3,4,5} and \ref{fig:1}a and \ref{fig:1} and later", 'thy_nos')
        self.assertIn(r"\hyperref[fig:thy_nos_1]{Figs.~\ref*{fig:thy_nos_1}--\ref*{fig:thy_nos_2}}, \hyperref[fig:thy_nos_4]{\ref*{fig:thy_nos_4}}", converted)
        self.assertIn(r"Tables~\hyperref[tab:thy_nos_1]{\ref*{tab:thy_nos_1}}, \hyperref[tab:thy_nos_3]{\ref*{tab:thy_nos_3}--\ref*{tab:thy_nos_5}}", converted)
        self.assertIn(r"\hyperref[fig:thy_nos_1]{Fig.~\ref*{fig:thy_nos_1}(a)} and", converted)
        self.assertIn(r"\hyperref[fig:thy_nos_1]{Fig.~\ref*{fig:thy_nos_1}} and later", converted)

    def test_entire_consecutive_figure_range_is_one_hyperlink(self):
        source = r"Figs. $\ref{fig:13-17}$; $\ref{fig:1,3,4}$; Eqs. $\ref{eq:4,5}$."
        result = conv.convert_figure_and_equation_refs(source, 'cha')
        self.assertIn(r"\hyperref[fig:cha_13]{Figs.~\ref*{fig:cha_13}--\ref*{fig:cha_17}}", result)
        self.assertIn(r"\hyperref[fig:cha_1]{Figs.~\ref*{fig:cha_1}}, \hyperref[fig:cha_3]{\ref*{fig:cha_3}--\ref*{fig:cha_4}}", result)
        self.assertIn(r"Eqs.~(\hyperref[eq:cha_4]{\ref*{eq:cha_4}--\ref*{eq:cha_5}})", result)
        self.assertNotIn(r"Figs.~\hyperref", result)

    def test_equation_citator_abbreviated_ranges(self):
        self.assertEqual(conv.expand_reference_tags('1.1~3, 1.5'), ['1.1','1.2','1.3','1.5'])
        self.assertEqual(conv.expand_reference_tags('B.1~3'), ['B.1','B.2','B.3'])
        self.assertEqual(conv.expand_reference_tags('3-5, 9, 11-12'), ['3','4','5','9','11','12'])

    def test_plugin_native_cross_file_footnote_and_no_double_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'Theory.md').write_text('---\nLatex Type: Chapter\n---\n')
            (root/'Microwave_Control_of_Transmons.md').write_text(
                '---\nLatex Type: Section\nLatex Parent: Theory\n---\n\n'
                '$$x=1 \\tag{3}$$\n$$y=2 \\tag{4}$$\n$$z=3 \\tag{5}$$\n')
            src=root/'Report.md'
            src.write_text('---\nLatex Type: Chapter\n---\n\n'
                '[^1]: [[Microwave Control of Transmons]]\n\n'
                r'See \ref{eq:1^{3~5}} and Eqs. (3-5) of [[Microwave Control of Transmons]].' + '\n')
            state=conv.ConversionState()
            index=conv.build_project_index(root,src,state)
            tex=conv.convert_markdown_to_latex(src.read_text(),src,index,state)
            target=r'Eqs.~(\hyperref[eq:thy_mis_3]{\ref*{eq:thy_mis_3}--\ref*{eq:thy_mis_5}})'
            self.assertEqual(tex.count(target),2)
            self.assertNotIn('[^1]:',tex)
            self.assertNotIn('[[',tex)
            self.assertEqual(state.warning_count,0)

    def test_invalid_same_note_reference_rejected_by_strict_mode(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/'Report.md'
            src.write_text('---\nLatex Type: Chapter\n---\n\n\\ref{eq:99}\n')
            result=subprocess.run([sys.executable,str(CONVERTER),str(src),'--root',str(root),'--strict'],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,'')
            self.assertIn("equation tag '99' not found",result.stderr)

    def test_missing_figures_tables_rejected_by_strict_mode(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/'Report.md'
            src.write_text('---\nLatex Type: Chapter\n---\n\n\\ref{fig:9} and \\ref{table:8}\n')
            result=subprocess.run([sys.executable,str(CONVERTER),str(src),'--strict'],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn("figure tag '9' not found",result.stderr)
            self.assertIn("table tag '8' not found",result.stderr)

    def test_parent_prefix_direct_ref_keeps_existing_single_style(self):
        self.assertEqual(conv.convert_figure_and_equation_refs(r'Eq. \ref{eq:1}', 'thy_nos'),
                         r'\hyperref[eq:thy_nos_1]{Eq.~(\ref*{eq:thy_nos_1})}')


    def test_first_reference_moves_default_figure_to_first_paragraph(self):
        note = r"""---
Latex Type: Chapter
---

## Example
First figure citation \ref{fig:1}, and also \ref{fig:2}.

Later discussion.

![[plot1.png|fig:1|desc:**First.** Caption.|500]]
![[plot2.png|fig:2|desc:**Second.** Caption.|500]]
"""
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'Figures.md'
            src.write_text(note)
            st=conv.ConversionState()
            idx=conv.build_project_index(Path(tmp),src,st)
            tex=conv.convert_markdown_to_latex(note,src,idx,st,figure_placement_mode="first")
        self.assertEqual(st.warning_count,0)
        self.assertEqual(tex.count(r'\begin{figure}[!t]'),2)
        self.assertNotIn(r'\begin{figure}[H]', tex)
        self.assertLess(tex.index(r'\label{fig:fis_1}'),tex.index('Later discussion.'))
        self.assertLess(tex.index(r'\label{fig:fis_2}'),tex.index('Later discussion.'))
        self.assertIn(r'\hyperref[fig:fis_1]',tex)

    def test_default_figure_stays_between_adjacent_paragraphs(self):
        # A standalone Obsidian embed can be surrounded by single newlines, not
        # empty lines. Its removal must not merge the before/after paragraphs.
        note = r"""---
Latex Type: Chapter
---

## Demo
Figure mentioned here \ref{fig:1}.
![[example.pdf|fig:1|desc:**Anchor caption.** Body.]]
The next paragraph cites equations instead.
"""
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'Figures.md';source.write_text(note)
            state=conv.ConversionState();idx=conv.build_project_index(Path(d),source,state)
            tex=conv.convert_markdown_to_latex(note,source,idx,state)
        self.assertEqual(state.warning_count,0)
        self.assertEqual(tex.count(r'\begin{figure}[!t]'),1)
        self.assertLess(tex.index('Figure mentioned here'),tex.index(r'\begin{figure}[!t]'))
        self.assertLess(tex.index(r'\end{figure}'),tex.index('The next paragraph cites'))

    def test_top_only_default_excludes_float_only_pages_and_keeps_explicit_options(self):
        """An ordinary top figure must not request a separate float-only page."""
        note = '![[' + 'art.pdf|fig:1|desc:**Caption.** Text.' + ']]'
        for mode in ('first', 'top'):
            with self.subTest(mode=mode):
                out = conv.convert_figures(note, 'demo', conv.ConversionState(), mode)
                self.assertIn(r'\begin{figure}[!t]', out)
                self.assertNotIn(r'\begin{figure}[!tp]', out)
        # The author's exceptions remain available; do not change them globally.
        out = conv.convert_figures(note.replace(']]', '|place:near]]'), 'demo', conv.ConversionState())
        self.assertIn(r'\begin{figure}[!htbp]', out)
        wide = conv.convert_figures(note.replace(']]', '|span:both]]'), 'demo', conv.ConversionState())
        self.assertIn(r'\begin{figure*}[!t]', wide)

    def test_explicit_here_figure_fits_here_or_starts_next_page_with_following_text(self):
        import shutil, subprocess
        if not shutil.which('pdflatex') or not shutil.which('pdftotext'):
            self.skipTest('pdflatex and pdftotext are required for page layout verification')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'Chapters'/'Figures').mkdir(parents=True)
            (root/'graphic.tex').write_text(r'\documentclass{standalone}\begin{document}\rule{3in}{1.9in}\end{document}')
            def compile_pdf(name):
                result=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',name+'.tex'],
                                      cwd=root,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout[-2000:])
                self.assertNotIn('Float too large for page',result.stdout)
                self.assertNotIn('Overfull \\vbox',result.stdout)
            compile_pdf('graphic')
            (root/'graphic.pdf').replace(root/'Chapters'/'Figures'/'graphic.pdf')
            preamble=r"""\documentclass[a4paper,11pt,BCOR=10mm,DIV=12,headinclude,headheight=16mm,oneside,onecolumn,open=any,parskip=half]{scrbook}
\usepackage[T1]{fontenc}\usepackage{lmodern}
\usepackage[onehalfspacing,nodisplayskipstretch]{setspace}
\usepackage{caption,graphicx,float,placeins,hyperref}
\begin{document}
"""
            for pushed in (False, True):
                with self.subTest(pushed=pushed):
                    filler=r'\noindent STARTER.\par\vspace*{0.60\textheight}' if pushed else 'STARTER.'
                    note=("---\nLatex Type: Chapter\n---\n\n## Demo\n"+filler+
                          "\n\nMention this figure \ref{fig:1} in a paragraph.\n"
                          "![[graphic.pdf|fig:1|desc:**ANCHORCAPTION.** Example figure.|place:here]]\n"
                          "AFTERPROSE must be printed after the caption.\n")
                    source=root/'Figures.md';source.write_text(note)
                    state=conv.ConversionState();idx=conv.build_project_index(root,source,state)
                    body=conv.convert_markdown_to_latex(note,source,idx,state)
                    self.assertEqual(state.warning_count,0)
                    self.assertLess(body.index(r'\end{figure}'),body.index('AFTERPROSE'))
                    (root/'main.tex').write_text(preamble+body+'\n\\end{document}\n')
                    compile_pdf('main');compile_pdf('main')
                    extracted=subprocess.check_output(['pdftotext','-layout','main.pdf','-'],cwd=root,text=True)
                    pages=[page for page in extracted.split('\f') if page.strip()]
                    if pushed:
                        self.assertGreaterEqual(len(pages),2)
                        self.assertIn('Mention this figure',pages[0])
                        self.assertIn('ANCHORCAPTION',pages[1])
                        self.assertIn('AFTERPROSE',pages[1])
                        self.assertLess(pages[1].index('ANCHORCAPTION'),pages[1].index('AFTERPROSE'))
                    else:
                        self.assertIn('ANCHORCAPTION',pages[0])
                        self.assertIn('AFTERPROSE',pages[0])
                        self.assertLess(pages[0].index('ANCHORCAPTION'),pages[0].index('AFTERPROSE'))

    def test_section_directive_keeps_figure_at_source_and_adds_barrier(self):
        note = r"""---
Latex Type: Chapter
---

## First section
Figure referenced \ref{fig:1} near the beginning.

Body after the citation.

![[plot.png|fig:1|desc:**Comparison.** Caption.|500|place:section]]

## Second section
New section text.
"""
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'Figures.md'
            src.write_text(note)
            st=conv.ConversionState()
            idx=conv.build_project_index(Path(tmp),src,st)
            tex=conv.convert_markdown_to_latex(note,src,idx,st)
        self.assertEqual(st.warning_count,0)
        self.assertIn(r'\begin{figure}[H]',tex)
        self.assertLess(tex.index('Body after the citation.'),tex.index(r'\begin{figure}[H]'))
        self.assertLess(tex.index(r'\end{figure}'),tex.index(r'\FloatBarrier'))
        self.assertLess(tex.index(r'\FloatBarrier'),tex.index(r'\section{Second section}'))

    def test_global_switch_top_near_section_here(self):
        data=r'First citation \ref{fig:1}.\n\nLater.\n\n![[plot.png|fig:1|desc:**Test.** Caption.|300]]'.replace(r'\n','\n')
        for mode, latex in [('top',r'\begin{figure}[!t]'),('near',r'\begin{figure}[!htbp]'),
                            ('section',r'\begin{figure}[H]'),('here',r'\begin{figure}[H]')]:
            with self.subTest(mode=mode):
                st=conv.ConversionState()
                tex=conv.convert_figures(data,'fis',st,mode)
                self.assertIn(latex,tex)
                self.assertEqual(tex.count(r'\FloatBarrier'),int(mode=='section'))
                self.assertEqual(st.warning_count,0)

    def test_first_reference_range_includes_second_image(self):
        data=r'Compare \ref{fig:1,2}.\n\nBetween.\n\n![[a.png|fig:1|desc:**A.** A.]]\n![[b.png|fig:2|desc:**B.** B.]]'.replace(r'\n','\n')
        st=conv.ConversionState()
        result=conv.relocate_figures_to_first_reference(data,'first',st)
        self.assertLess(result.index('![[a.png'),result.index('Between.'))
        self.assertLess(result.index('![[b.png'),result.index('Between.'))
        self.assertEqual(st.warning_count,0)

    def test_figure_modes_in_self_contained_section_fixture(self):
        """Section-anchored and first-reference figures work without thesis assets."""
        note = r"""---
Latex Type: Section
Latex Parent: Theory
---
## 2) Pulse Envelopes
The pulse-shape optimization compares $\ref{fig:1}$.

![[pulses.svg|center|fig:1|desc:**Pulses.** Comparison.|700|place:section]]

## 3) Virtual Z Gates
These require no physical microwave waveform.

## 7) Control-Chain Imperfections
As shown in $\ref{fig:2}$, the control chain introduces errors.

**Digital waveform generation** describes the first stage.

![[control.svg|center|fig:2|desc:**Control chain.** Schematic.|700|place:first]]
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'Theory.md').write_text('---\nLatex Type: Chapter\n---\n', encoding='utf-8')
            source = root/'Microwave Control of Transmons.md'
            source.write_text(note, encoding='utf-8')
            state = conv.ConversionState()
            index = conv.build_project_index(root, source, state)
            tex = conv.convert_markdown_to_latex(note, source, index, state)
        self.assertEqual(state.warning_count, 0)
        self.assertEqual(tex.count(r'\begin{figure}[H]'), 1)
        self.assertEqual(tex.count(r'\begin{figure}[!t]'), 1)
        self.assertIn(r'\FloatBarrier', tex)
        self.assertLess(tex.index('The pulse-shape optimization'), tex.index(r'\label{fig:thy_mis_1}'))
        self.assertLess(tex.index(r'\FloatBarrier'), tex.index(r'\subsection{Virtual Z Gates}'))
        self.assertLess(tex.index(r'\label{fig:thy_mis_2}'), tex.index(r'\textbf{Digital waveform generation}'))

    def test_cli_switch_invalid_mode_and_unknown_directive(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'Figures.md'
            src.write_text('---\nLatex Type: Chapter\n---\n\n![[plot.png|fig:1|desc:**Test.**|place:wrong]]\n')
            out=subprocess.run([sys.executable,str(CONVERTER),str(src),'--figure-placement','top','--strict'],capture_output=True,text=True)
            self.assertEqual(out.returncode,2)
            self.assertIn("unknown figure placement 'wrong'",out.stderr)
            self.assertEqual(out.stdout,'')


    def test_first_placement_preserves_figure_counter_order(self):
        note = r"""---
Latex Type: Chapter
---

## Example
Both figures are mentioned: \ref{fig:1} and \ref{fig:2}.

Later explanation.

![[first.png|fig:1|desc:**First.** Text.|place:section]]

![[second.png|fig:2|desc:**Second.** Text.|place:first]]
"""
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'Figures.md';src.write_text(note)
            state=conv.ConversionState(warnings_enabled=False)
            idx=conv.build_project_index(Path(td),src,state)
            tex=conv.convert_markdown_to_latex(note,src,idx,state)
        self.assertLess(tex.index(r'\label{fig:fis_1}'),tex.index(r'\label{fig:fis_2}'))
        self.assertIn('Later explanation.',tex)
        self.assertGreaterEqual(state.warning_count,1)

    def test_first_reference_will_not_move_across_appendix_heading(self):
        note = r"""---
Latex Type: Chapter
---

The appendix figure \ref{fig:A.1} is described here.

## Appendix A: Additional Results

![[appendix.png|fig:A.1|desc:**Appendix figure.** Text.|place:first]]
"""
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'Figures.md';src.write_text(note)
            state=conv.ConversionState(warnings_enabled=False)
            idx=conv.build_project_index(Path(td),src,state)
            tex=conv.convert_markdown_to_latex(note,src,idx,state)
        self.assertLess(tex.index(r'\section{Additional Results}'),tex.index(r'\label{fig:fis_A.1}'))
        self.assertGreaterEqual(state.warning_count,1)



    def test_article_mode_headings_and_label_references(self):
        source = r"""---
Latex Type: Article
---

## Introduction

As in \ref{eq:1}, we study pulse control.

$$x=1 \tag{1}$$

### Methods

Details.

#### Experimental control

More details.
"""
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'Calibration Paper.md';p.write_text(source)
            state=conv.ConversionState();idx=conv.build_project_index(root,p,state)
            tex=conv.convert_markdown_to_latex(source,p,idx,state)
        self.assertEqual(state.warning_count,0)
        self.assertTrue(tex.startswith(r'\phantomsection\label{doc:car}'))
        self.assertIn(r'\section{Introduction}',tex)
        self.assertIn(r'\subsection{Methods}',tex)
        self.assertIn(r'\subsubsection{Experimental control}',tex)
        self.assertNotIn(r'\chapter{Calibration Paper}',tex)
        self.assertNotIn(r'\section{Calibration Paper}',tex)
        self.assertIn(r'\label{eq:car_1}',tex)
        self.assertIn(r'\hyperref[eq:car_1]',tex)

    def test_article_uses_standard_chapters_figures_default(self):
        source = "---\nLatex Type: Article\n---\n\n## Intro\n\n![[plot.svg|fig:1|desc:**Plot.** Caption.]]\n"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "Paper.md"
            path.write_text(source)
            state = conv.ConversionState()
            index = conv.build_project_index(root, path, state)
            latex = conv.convert_markdown_to_latex(source, path, index, state)
            self.assertEqual(state.warning_count, 0)
            self.assertIn(r"\includegraphics{Chapters/Figures/plot.pdf}", latex)
            self.assertNotIn(r"\includegraphics{Figures/plot.pdf}", latex)
            override = conv.convert_markdown_to_latex(source, path, index, conv.ConversionState(), figure_dir="Custom/Artwork")
            self.assertIn(r"\includegraphics{Custom/Artwork/plot.pdf}", override)

    def test_artwork_file_types_and_caption_aware_figure_embedding(self):
        data = ('![[Plot.svg|fig:1|desc:**Plot.** Plot caption.|700]]\n'
                '![[Raster.png|fig:2|desc:**Raster.** Raster caption.|300]]\n'
                '![[Photo.JPEG|fig:3|desc:**Photo.** Photo caption.|200]]\n'
                '![[Other.pdf|fig:4|desc:**Other.** Other caption.|200]]\n')
        state=conv.ConversionState();tex=conv.convert_figures(data,'pap',state,'top','My Images')
        self.assertEqual(state.warning_count,0)
        for name in ['Plot.pdf','Raster.png','Photo.JPEG','Other.pdf']:
            self.assertIn(r'\sbox{\mdToLatexNaturalImageBox}{\includegraphics{My Images/'+name+'}',tex)
            self.assertIn(r'\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]{My Images/'+name+'}',tex)
        self.assertIn(r'\setbox\mdToLatexCaptionBox=\vbox{',tex)
        self.assertIn(r'\newdimen\mdToLatexFigureHeight',tex)
        self.assertNotIn(r'\dimen0',tex)
        self.assertIn(r'\mdToLatexFigureHeight=\dimexpr 0.96\textheight-',tex)
        self.assertIn(r'\ifdim\wd\mdToLatexNaturalImageBox>\linewidth',tex)
        self.assertIn(r'\ifdim\dimexpr\ht\mdToLatexNaturalImageBox+\dp\mdToLatexNaturalImageBox\relax>',tex)
        self.assertIn(r'\usebox{\mdToLatexNaturalImageBox}',tex)
        self.assertNotIn(r'\textwidth',tex)
        self.assertNotIn('Plot.png',tex)

    def test_caption_is_measured_once_before_graphic(self):
        state=conv.ConversionState()
        tex=conv.convert_figures('![[plot.svg|fig:3|desc:**Long caption.** Multiple lines of description.|700]]', 'pap', state)
        self.assertEqual(state.warning_count,0)
        self.assertEqual(tex.count(r'\caption['),1)
        self.assertEqual(tex.count(r'\label{fig:pap_3}'),1)
        self.assertEqual(tex.count(r'\usebox{\mdToLatexCaptionBox}'),1)
        self.assertLess(tex.index(r'\caption['),tex.index(r'\sbox{\mdToLatexNaturalImageBox}'))
        self.assertLess(tex.index(r'\sbox{\mdToLatexNaturalImageBox}'),tex.index(r'\usebox{\mdToLatexCaptionBox}'))
        self.assertIn(r'\dimexpr 0.96\textheight-\ht\mdToLatexCaptionBox-\dp\mdToLatexCaptionBox-\baselineskip',tex)

    def test_figure_needs_no_size_token_or_manual_height_mode(self):
        state=conv.ConversionState()
        page=conv.convert_figures('![[pulses.svg|fig:1|desc:**Pulse spectra.** Caption.]]','pap',state)
        normal=conv.convert_figures('![[bloch.svg|fig:2|desc:**Bloch sphere.** Caption.]]','pap',state)
        self.assertEqual(state.warning_count,0)
        self.assertNotIn('size:',page+normal)
        self.assertNotIn('0.70\\textheight',page+normal)
        self.assertNotIn('0.85\\textheight',page+normal)
        for tex in (page,normal):
            self.assertIn(r'\mdToLatexFigureHeight=\dimexpr 0.96\textheight-',tex)
            self.assertIn(r'\ifdim\wd\mdToLatexNaturalImageBox>\linewidth',tex)
            self.assertIn(r'\usebox{\mdToLatexNaturalImageBox}',tex)

    def test_native_image_width_is_not_upscaled_in_latex(self):
        import shutil, subprocess, re
        if not shutil.which('pdflatex'):
            self.skipTest('pdflatex is unavailable')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); assets=root/'Chapters'/'Figures'; assets.mkdir(parents=True)
            (root/'small.tex').write_text(r'\documentclass{standalone}\begin{document}\rule{2in}{1.5in}\end{document}')
            def latex(stem):
                return subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',stem+'.tex'],cwd=root,capture_output=True,text=True)
            proc=latex('small'); self.assertEqual(proc.returncode,0,proc.stdout[-1200:])
            (root/'small.pdf').replace(assets/'small.pdf')
            state=conv.ConversionState()
            figure=conv.convert_figures('![[small.svg|fig:1|desc:**Small.** Figure.]]','s',state)
            self.assertEqual(state.warning_count,0)
            figure=figure.replace(r'    \ifdim\wd\mdToLatexNaturalImageBox>\linewidth',
                                  r'    \typeout{FIGWIDTH=\the\wd\mdToLatexNaturalImageBox}'+'\n'+
                                  r'    \ifdim\wd\mdToLatexNaturalImageBox>\linewidth')
            figure=figure.replace(r'            \usebox{\mdToLatexNaturalImageBox}',
                                  r'            \typeout{FIG-NATIVE}'+'\n'+r'            \usebox{\mdToLatexNaturalImageBox}')
            (root/'main.tex').write_text(r'\documentclass[a4paper,11pt]{scrbook}\usepackage{graphicx,caption,float}\begin{document}'+ '\n'+figure+r'\end{document}')
            proc=latex('main'); self.assertEqual(proc.returncode,0,proc.stdout[-1200:])
            match=re.search(r'FIGWIDTH=([\d.]+)pt',proc.stdout)
            self.assertIsNotNone(match,proc.stdout[-1200:])
            self.assertGreater(float(match.group(1)),140)
            self.assertLess(float(match.group(1)),150)
            self.assertIn('FIG-NATIVE',proc.stdout)

    def test_only_oversized_artwork_uses_graphicx_scaling(self):
        import shutil, subprocess
        if not shutil.which('pdflatex'):
            self.skipTest('pdflatex is unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); artwork=root/'Chapters'/'Figures'; artwork.mkdir(parents=True)
            def run(stem):
                return subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',stem+'.tex'],cwd=root,capture_output=True,text=True)
            for name,w,h in [('small',2,1),('fits',5.7,5.0),('too_wide',7,2),('too_tall',3,8)]:
                (root/(name+'.tex')).write_text('\\documentclass{standalone}\\begin{document}\\rule{'+str(w)+'in}{'+str(h)+'in}\\end{document}')
                made=run(name); self.assertEqual(made.returncode,0,made.stdout[-1200:])
                (root/(name+'.pdf')).replace(artwork/(name+'.pdf'))
            note=''.join('![[%s.pdf|fig:%d|desc:**Comparison.** A caption.]]\n'% (n,i) for i,n in enumerate(('small','fits','too_wide','too_tall'),1))
            state=conv.ConversionState(); figures=conv.convert_figures(note,'fit',state)
            self.assertEqual(state.warning_count,0)
            # The diagnostic types are only printed in the executed TeX branch.
            figures=figures.replace(r'            \usebox{\mdToLatexNaturalImageBox}',
                  r'            \typeout{CHOSEN-NATIVE}'+'\n'+r'            \usebox{\mdToLatexNaturalImageBox}')
            figures=figures.replace(r'\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]',
                  r'\typeout{CHOSEN-SCALED}\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]')
            (root/'main.tex').write_text(r'\documentclass[a4paper,11pt,BCOR=10mm,DIV=12,headinclude,headheight=16mm,oneside,onecolumn,open=any,parskip=half]{scrbook}'+'\n'+r'\usepackage{graphicx,caption,float}\begin{document}'+'\n'+figures+'\n'+r'\end{document}')
            result=run('main'); self.assertEqual(result.returncode,0,result.stdout[-1800:])
            self.assertEqual(result.stdout.count('CHOSEN-NATIVE'),2,result.stdout[-1600:])
            self.assertEqual(result.stdout.count('CHOSEN-SCALED'),2,result.stdout[-1600:])
            self.assertNotIn('Float too large for page',result.stdout)
            self.assertNotIn('Overfull \vbox',result.stdout)

    def test_native_page_filling_plot_and_long_caption_fit_together(self):
        import shutil, subprocess
        if not shutil.which('pdflatex'):
            self.skipTest('pdflatex is unavailable')
        caption=(r'**Comparison of microwave pulse envelopes and their spectra.** '
                 r'(a) In-phase envelopes $I(t)$ for the square, shifted-cosine, Gaussian, '
                 r'DRAG, HD-DRAG and FAST-DRAG pulse families; dashed curves indicate derivative '
                 r'quadratures $Q(t)$ where applicable. (b) Corresponding baseband spectral '
                 r'magnitudes relative to the carrier frequency $\omega_d$. The shaded region '
                 r'indicates the leakage-sensitive frequency band near '
                 r'$\alpha/2\pi=-200\,\mathrm{MHz}$. All pulses have duration $T_g=10\,\mathrm{ns}$.')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); assets=root/'Chapters'/'Figures'; assets.mkdir(parents=True)
            def latex(stem):
                return subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',stem+'.tex'],cwd=root,capture_output=True,text=True)
            (root/'prepared.tex').write_text(r'\documentclass{standalone}\begin{document}\rule{5.88in}{6.1in}\end{document}')
            out=latex('prepared'); self.assertEqual(out.returncode,0,out.stdout[-1200:])
            (root/'prepared.pdf').replace(assets/'prepared.pdf')
            st=conv.ConversionState()
            tex=conv.convert_figures('![[prepared.pdf|fig:1|desc:'+caption+']]','p',st)
            self.assertEqual(st.warning_count,0)
            tex=tex.replace(r'            \usebox{\mdToLatexNaturalImageBox}',
                            r'            \typeout{CHOSEN-NATIVE}'+'\n'+r'            \usebox{\mdToLatexNaturalImageBox}')
            tex=tex.replace(r'\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]',
                            r'\typeout{CHOSEN-SCALED}\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]')
            pre=(r'\documentclass[a4paper,11pt,BCOR=10mm,DIV=12,headinclude,headheight=16mm,oneside,onecolumn,open=any,parskip=half]{scrbook}'+'\n'
                 +r'\usepackage[T1]{fontenc}\usepackage{lmodern}'+'\n'
                 +r'\usepackage[onehalfspacing,nodisplayskipstretch]{setspace}'+'\n'
                 +r'\usepackage{caption,graphicx,float}'+'\n'
                 +r'\DeclareCaptionLabelFormat{custom}{\textbf{#1 #2}}'+'\n'
                 +r'\DeclareCaptionFormat{custom}{#1#2\textup{\small#3}}'+'\n'
                 +r'\captionsetup{format=custom,labelformat=custom}'+'\n'
                 +r'\begin{document}'+'\n')
            (root/'main.tex').write_text(pre+tex+r'\end{document}')
            out=latex('main'); self.assertEqual(out.returncode,0,out.stdout[-1800:])
            self.assertIn('CHOSEN-NATIVE',out.stdout)
            self.assertNotIn('CHOSEN-SCALED',out.stdout)
            self.assertNotIn('Float too large for page',out.stdout)
            self.assertNotIn('Overfull \vbox',out.stdout)

    def test_tall_figure_with_long_caption_fits_scrbook_page(self):
        # Regression: graphicx overwrites \dimen0 during option processing,
        # formerly making a tall figure overflow by about 74 pt.
        import shutil
        import subprocess
        if not shutil.which('pdflatex'):
            self.skipTest('pdflatex is unavailable')
        caption = (r'**Comparison of microwave pulse envelopes and their spectra.** '
                   r'(a) In-phase envelopes $I(t)$ for the square, shifted-cosine, Gaussian, '
                   r'DRAG, HD-DRAG and FAST-DRAG pulse families; dashed curves indicate derivative '
                   r'quadratures $Q(t)$ where applicable. (b) Corresponding baseband spectral '
                   r'magnitudes relative to the carrier frequency $\omega_d$. The shaded region '
                   r'indicates the leakage-sensitive frequency band near '
                   r'$\alpha/2\pi=-200\,\mathrm{MHz}$. All pulses have duration $T_g=10\,\mathrm{ns}$.')
        source = '![[pulses.svg|center|fig:1|desc:' + caption + '|place:section|700]]'
        state = conv.ConversionState()
        figure = conv.convert_figures(source, 'th_mic', state)
        self.assertEqual(state.warning_count, 0)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'Chapters'/'Figures').mkdir(parents=True)
            # Generate a tall vector figure with approximately the source aspect ratio.
            (root/'pulses.tex').write_text(r'\documentclass{standalone}\begin{document}\rule{6in}{8in}\end{document}')
            def latex(stem):
                return subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', stem+'.tex'], cwd=root, capture_output=True, text=True)
            result = latex('pulses')
            self.assertEqual(result.returncode, 0, result.stdout[-1500:])
            (root/'pulses.pdf').replace(root/'Chapters'/'Figures'/'pulses.pdf')
            preamble = r'''\documentclass[a4paper,11pt,BCOR=10mm,DIV=12,headinclude,headheight=16mm,oneside,onecolumn,open=any,parskip=half]{scrbook}
\usepackage[T1]{fontenc}\usepackage{lmodern}
\usepackage[onehalfspacing,nodisplayskipstretch]{setspace}
\usepackage{caption,graphicx,float}
\usepackage[section]{placeins}
\usepackage{hyperref}
\DeclareCaptionLabelFormat{custom}{\textbf{#1 #2}}
\DeclareCaptionFormat{custom}{#1#2\textup{\small#3}}
\captionsetup{format=custom,labelformat=custom}
\begin{document}
\chapter{Theory}\section{Microwave Control}\subsection{Pulse Envelopes}
Some preceding discussion.\par
'''
            after = r'''\subsection{Virtual Z Gates}
This is the next subsection.
\end{document}
'''
            (root/'main.tex').write_text(preamble + figure + after)
            result = latex('main')
            self.assertEqual(result.returncode, 0, result.stdout[-1500:])
            self.assertNotIn('Float too large for page', result.stdout)
            self.assertNotIn('Overfull \\vbox', result.stdout)
            self.assertTrue((root/'main.pdf').is_file())

    def test_span_both_figures_and_compatibility(self):
        state=conv.ConversionState()
        tex=conv.convert_figures('![[wide.svg|fig:1|desc:**Wide.** Caption.|700|span:both]]','pap',state)
        self.assertIn(r'\begin{figure*}[!t]',tex)
        self.assertIn(r'\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]{Chapters/Figures/wide.pdf}',tex)
        self.assertEqual(state.warning_count,0)
        state=conv.ConversionState(warnings_enabled=False)
        conv.convert_figures('![[wide.svg|fig:1|desc:**Wide.** Caption.|span:both|place:here]]','pap',state)
        self.assertEqual(state.warning_count,1)

    def test_table_float_modes_remain_unchanged(self):
        headers=['Name','Value']; rows=[['A','1']]
        for mode, placement in [('top','!tbp'),('near','!htbp'),('section','!htbp'),('here','H')]:
            with self.subTest(mode=mode):
                state=conv.ConversionState()
                tex=conv.convert_table_block(headers,'| --- | --- |',rows,state,placement=mode)
                self.assertIn(r'\begin{table}['+placement+']',tex)
                self.assertEqual(state.warning_count,0)

    def test_article_table_default_and_hidden_options(self):
        markdown = """---
Latex Type: Article
---

## Data

> [!table: 1] Table 1. **Method comparison.** Example numbers.
> <!-- latex: place:top span:both width:fit cols:lXr -->
> | Method | Description | Count |
> | --- | --- | ---: |
> | RPE | Longer description | 5 |
"""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Calibration Paper.md';p.write_text(markdown)
            state=conv.ConversionState();idx=conv.build_project_index(Path(d),p,state)
            tex=conv.convert_markdown_to_latex(markdown,p,idx,state)
        self.assertEqual(state.warning_count,0)
        self.assertIn(r'\begin{table*}[!tp]',tex)
        self.assertIn(r'\begin{tabularx}{\linewidth}{lXr}',tex)
        self.assertIn(r'\label{tab:car_1}',tex)
        self.assertNotIn('<!-- latex:',tex)
        self.assertIn(r'\caption[Method comparison]',tex)
        # An ordinary article table floats; thesis tables still use [H].
        self.assertIn(r'\begin{table}[!tbp]',conv.convert_tables(
            '> [!table: 2] **Small.**\n> | A | B |\n> | --- | --- |\n> | x | y |',
            'car',conv.ConversionState(), table_placement='top'))

    def test_invalid_table_width_directives_warn(self):
        data = '> [!table: 1] **Bad.**\n> <!-- latex: width:fit cols:rr -->\n> | A | B |\n> | --- | --- |\n> | 1 | 2 |'
        state=conv.ConversionState(warnings_enabled=False)
        conv.convert_tables(data,'car',state,'top')
        self.assertGreaterEqual(state.warning_count,1)

    def test_cli_article_options(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/'Paper.md'
            src.write_text('---\nLatex Type: Article\n---\n\n## Intro\n\n![[plot.svg|fig:1|desc:**Vector.** Caption.|700]]\n')
            result=subprocess.run([sys.executable,str(CONVERTER),str(src),'--figure-dir','Graphics','--table-placement','top','--strict'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,msg=result.stderr)
            self.assertIn(r'\section{Intro}',result.stdout)
            self.assertIn(r'\includegraphics[width=\linewidth,height=\the\mdToLatexFigureHeight,keepaspectratio]{Graphics/plot.pdf}',result.stdout)
            self.assertIn(r'\sbox{\mdToLatexNaturalImageBox}{\includegraphics{Graphics/plot.pdf}}',result.stdout)

    def test_svg_pdf_batch_conversion_and_incremental(self):
        import subprocess
        script=Path(__file__).with_name('svg_to_pdf_batch.py')
        if not script.exists():
            self.skipTest('Standalone SVG batch script not present')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            svg=root/'Small Plot.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="30mm" viewBox="0 0 600 300"><rect width="600" height="300" fill="white"/><path d="M 10 290 L 590 10" stroke="black" stroke-width="3" fill="none"/></svg>')
            (root/'raster.png').write_bytes(b'not a real raster')
            dry=subprocess.run([sys.executable,str(script),str(root),'--dry-run'],capture_output=True,text=True)
            self.assertEqual(dry.returncode,0,msg=dry.stderr)
            self.assertIn('WOULD EXPORT Small Plot.svg',dry.stdout)
            self.assertFalse(svg.with_suffix('.pdf').exists())
            if not __import__('shutil').which('inkscape'):
                self.skipTest('Inkscape not available')
            run=subprocess.run([sys.executable,str(script),str(root)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,msg=run.stderr)
            pdf=svg.with_suffix('.pdf')
            self.assertTrue(pdf.exists())
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF-'))
            second=subprocess.run([sys.executable,str(script),str(root)],capture_output=True,text=True)
            self.assertIn('SKIP Small Plot.svg',second.stdout)
            self.assertTrue((root/'raster.png').exists())
            # SVG has explicitly declared physical dimensions; verify PDF media box.
            import fitz
            doc=fitz.open(pdf);rect=doc[0].rect;doc.close()
            self.assertAlmostEqual(rect.width,60*72/25.4,delta=2.5)
            self.assertAlmostEqual(rect.height,30*72/25.4,delta=2.5)

    def test_svg_pdf_batch_subfolders(self):
        import subprocess
        script=Path(__file__).with_name('svg_to_pdf_batch.py')
        if not script.exists():
            self.skipTest('Standalone SVG batch script not present')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sub=root/'subs';sub.mkdir()
            (root/'a.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"/>')
            (sub/'b.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"/>')
            no_recursive=subprocess.run([sys.executable,str(script),str(root),'--dry-run'],capture_output=True,text=True)
            self.assertIn('a.svg',no_recursive.stdout)
            self.assertNotIn('b.svg',no_recursive.stdout)
            recursive=subprocess.run([sys.executable,str(script),str(root),'--dry-run','--recursive'],capture_output=True,text=True)
            self.assertIn('b.svg',recursive.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
