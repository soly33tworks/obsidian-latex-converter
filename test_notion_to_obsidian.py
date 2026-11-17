from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from notion_to_obsidian import (CitationResolver, default_bbt_key, process_export,
                               extract_zip, canonical_doi, convert_doi_citations)

ROOT = Path(__file__).resolve().parent
ACTUAL_STYLE_PAGE = (
    '# Pulse calibration\n\nFor an ideal resonant two-level drive, the target rotation is\n\n'
    '$$\nR_x(\\theta)=\\exp[-i\\theta\\sigma_x/2].\n$$\n\n'
    'The rotation in Equation 1 is the reference operation in this illustrative example '
    '[[1]](https://doi.org/10.1017/CBO9780511976667).\n\n'
    'As shown in Figure 1, the Gaussian-shaped drive envelope is a schematic pulse, not experimental data.\n\n'
    '![Illustrative drive envelope. Normalized Gaussian-shaped pulse over a 20 ns window.](Pulse%20calibration/demo_pulse.svg)\n\n'
    'Illustrative drive envelope. Normalized Gaussian-shaped pulse over a 20 ns window.\n\n'
    'The corresponding parameters are listed in Table 1.\n\n'
    'Table 1. **Example pulse settings.** Illustrative values, not calibrated hardware parameters.\n\n'
    '| Parameter | Value |\n| --- | --- |\n| Pulse window | 20 ns |\n| Gaussian standard deviation | 4 ns |\n'
)
DOI = '10.1017/cbo9780511976667'
KEY = 'nielsenQuantumComputationQuantum2010'
METADATA = {'title': 'Quantum Computation and Quantum Information', 'author': 'Nielsen', 'year': '2010'}


def mock_zotero(method, params):
    assert method == 'item.search'
    if params[0][0][0] == 'DOI':
        return [{'citekey': KEY, 'DOI': DOI.upper(), 'title': METADATA['title']}]
    return []


def resolver(zotero=True):
    return CitationResolver(use_zotero=zotero, metadata_lookup=lambda doi: METADATA,
                            rpc=mock_zotero if zotero else None)


class NotionBridgeTests(unittest.TestCase):
    def test_actual_export_direct_filename_and_live_zotero_mock(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / 'out'
            archive = Path(td) / '12345678-1234-4234-8234-123456789abc_ExportBlock-abcdefab-cdef-4abc-8def-abcdefabcdef.zip'
            with zipfile.ZipFile(archive, 'w') as f:
                f.writestr('Example Export/Pulse calibration 11223344556677889900aabbccddeeff.md', ACTUAL_STYLE_PAGE)
                f.writestr('Example Export/Pulse calibration/demo_pulse.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"/>')
            warnings = []
            results = process_export(archive, dest, 'Article', None, 'here', warnings, resolver())
            self.assertEqual(warnings, [])
            self.assertEqual([p.name for p in results], ['Pulse calibration.md'])
            md = results[0].read_text()
            for value in ['Latex Type: Article', '## Pulse calibration', r'\tag{1}',
                          r'$\ref{eq:1}$', r'$\ref{fig:1}$', r'$\ref{table:1}$',
                          'fig:1|desc:Illustrative drive envelope.', '> [!table: 1]', f'[@{KEY}]']:
                self.assertIn(value, md)
            self.assertNotIn('[[1]](https://', md)
            self.assertEqual(md.count('Illustrative drive envelope. Normalized Gaussian-shaped pulse'), 1)
            self.assertTrue((dest / 'Chapters' / 'Figures' / 'demo_pulse.svg').exists())
            process_export(archive, dest, 'Article', None, 'here', [], resolver())
            self.assertEqual(sorted(p.name for p in (dest / 'Chapters' / 'Figures').iterdir()), ['demo_pulse.svg'])

    def test_doi_link_converts_and_keeps_web_links(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            note = root / 'References.md'
            note.write_text('Citation [1](https://doi.org/10.1017/CBO9780511976667). '
                            'Again [1](https://dx.doi.org/10.1017/CBO9780511976667). '
                            'Website [2](https://example.com).\n')
            warnings=[]
            result = process_export(note, root/'vault', 'Article', None, 'here', warnings, resolver())[0].read_text()
            self.assertEqual(warnings, [])
            self.assertEqual(result.count(f'[@{KEY}]'), 2)
            self.assertIn('[2](https://example.com)', result)

    def test_bib_key_resolution_without_map_and_without_doi_field(self):
        with tempfile.TemporaryDirectory() as td:
            bib = Path(td) / 'MAIN.bib'
            bib.write_text('@book{nielsenQuantumComputationQuantum2010,\n'
                           '  title={Quantum Computation and Quantum Information},\n'
                           '  author={Nielsen, Michael A. and Chuang, Isaac L.},\n'
                           '  year={2010},\n}\n')
            r = CitationResolver([bib], use_zotero=False, metadata_lookup=lambda doi: METADATA)
            self.assertEqual(r.resolve(DOI), (KEY, 'Zotero bibliography'))

    def test_bib_2010_matches_doi_metadata_2012(self):
        with tempfile.TemporaryDirectory() as td:
            bib = Path(td) / 'MAIN.bib'
            bib.write_text('@book{nielsenQuantumComputationQuantum2010,\n'
                           ' title={Quantum Computation and Quantum Information},\n'
                           ' author={Nielsen, Michael A. and Chuang, Isaac L.},\n'
                           ' year={2010},\n}\n')
            metadata2012 = {**METADATA, 'year': '2012'}
            r = CitationResolver([bib], use_zotero=False, metadata_lookup=lambda doi: metadata2012)
            self.assertEqual(r.resolve(DOI), (KEY, 'Zotero bibliography'))

    def test_zotero_title_match_2010_versus_doi_2012(self):
        seen = []
        metadata2012 = {**METADATA, 'year': '2012'}
        def rpc(method, params):
            seen.append(params)
            terms = params[0]
            if terms[0][0] == 'DOI':
                return []  # Zotero record is missing the DOI
            return [{'citekey': KEY, 'title': METADATA['title'],
                     'author': [{'family': 'Nielsen'}, {'family': 'Chuang'}],
                     'issued': {'date-parts': [[2010]]}}]
        r = CitationResolver(use_zotero=True, metadata_lookup=lambda doi: metadata2012, rpc=rpc)
        self.assertEqual(r.resolve(DOI), (KEY, 'Zotero Better BibTeX'))
        self.assertTrue(seen)

    def test_bib_doi_priority_over_generated_formula(self):
        with tempfile.TemporaryDirectory() as td:
            bib = Path(td) / 'MAIN.bib'
            bib.write_text('@book{userCustomPinnedKey,\n title={Different Title},\n doi={10.1017/CBO9780511976667}\n}\n')
            r = CitationResolver([bib], use_zotero=False, metadata_lookup=lambda doi: None)
            self.assertEqual(r.resolve(DOI), ('userCustomPinnedKey', 'Zotero bibliography'))

    def test_default_formula_matches_nielsen_demo(self):
        self.assertEqual(default_bbt_key(METADATA), KEY)

    def test_unmatched_key_warns_instead_of_fabricating(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            note = root / 'References.md'
            note.write_text('Read [1](https://doi.org/10.1234/example).\n')
            warnings=[]
            r = CitationResolver(use_zotero=False, metadata_lookup=lambda doi: None)
            md = process_export(note, root/'vault', 'Article', None, 'here', warnings, r)[0].read_text()
            self.assertIn('[1](https://doi.org/10.1234/example)', md)
            self.assertEqual(len(warnings), 1)
            self.assertIn('cannot resolve DOI', warnings[0])

    def test_generated_key_is_flagged_as_guess(self):
        r = CitationResolver(use_zotero=False, metadata_lookup=lambda doi: METADATA,
                             allow_key_estimates=True)
        warnings=[]
        result = convert_doi_citations('See [[1]](https://doi.org/10.1017/CBO9780511976667)', Path('demo.md'), r, warnings)
        self.assertEqual(result, f'See [@{KEY}]')
        self.assertEqual(len(warnings), 1)
        self.assertIn('guessed citation key', warnings[0])

    def test_missing_zotero_key_does_not_guess_by_default(self):
        r = CitationResolver(use_zotero=False, metadata_lookup=lambda doi: {**METADATA, 'year': '2012'})
        warnings = []
        original = 'See [[1]](https://doi.org/10.1017/CBO9780511976667)'
        result = convert_doi_citations(original, Path('demo.md'), r, warnings)
        self.assertEqual(result, original)
        self.assertEqual(len(warnings), 1)
        self.assertIn('cannot resolve DOI', warnings[0])

    def test_conflicting_same_number_different_dois(self):
        r = CitationResolver(use_zotero=False, metadata_lookup=lambda doi: METADATA)
        warnings=[]
        text = '[1](https://doi.org/10.1017/CBO9780511976667), [1](https://doi.org/10.1234/example)'
        converted = convert_doi_citations(text, Path('demo.md'), r, warnings)
        self.assertIn('10.1234/example', converted)
        self.assertTrue(any('different DOIs' in w for w in warnings))

    def test_skip_fenced_code_and_preserve_external_link(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            note = root / 'Some Page 11111111111111111111111111111111.md'
            note.write_text('```python\n# Heading\nFigure 1\n```\n\n$$\nx=1\n$$\n\n[Site](https://example.com)\n')
            result = process_export(note, root/'vault', 'Article', None, 'here', [], resolver())[0].read_text()
            self.assertIn('```python\n# Heading\nFigure 1\n```', result)
            self.assertIn('[Site](https://example.com)', result)
            self.assertIn(r'x=1\tag{1}', result)

    def test_relative_page_links_convert_to_wikilinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            origin = root/'source'; origin.mkdir()
            (origin / 'A 11111111111111111111111111111111.md').write_text('[Continue](B%2022222222222222222222222222222222.md)\n')
            (origin / 'B 22222222222222222222222222222222.md').write_text('Some content\n')
            output = process_export(origin, root/'output', 'Article', None, 'first', [], resolver())
            self.assertEqual(len(output), 2)
            self.assertIn('[[B|Continue]]', (root/'output'/'A.md').read_text())

    def test_uncaptioned_table_remains_plain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            note=root/'Input.md'
            note.write_text('| A | B |\n| --- | --- |\n| one | two |\n')
            warnings=[]
            result = process_export(note, root/'vault', 'Article', None, 'here', warnings, resolver())[0].read_text()
            self.assertIn('| A | B |', result)
            self.assertTrue(any('no preceding' in w for w in warnings))

    def test_bad_zip_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); archive = root/'bad.zip'
            with zipfile.ZipFile(archive, 'w') as f:
                f.writestr('../escaped.md', 'unsafe')
            with self.assertRaises(ValueError):
                extract_zip(archive, root/'out')

    def test_output_not_inside_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'A.md').write_text('hello')
            with self.assertRaises(ValueError):
                process_export(root, root/'out', 'Article', None, 'here', [], resolver())

if __name__ == '__main__':
    unittest.main()
