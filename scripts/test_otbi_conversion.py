"""Offline OTBI conversion regressions. All catalog data is synthetic."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib
import zipfile
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'skills/dia-otbi-to-bipublisher-sql/scripts/convert_otbi_catalog.py'
spec = importlib.util.spec_from_file_location('converter', HELPER)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def expr(kind, text='', op='', children=''):
    return f'<sawx:expr xsi:type="{kind}"' + (f' op="{op}"' if op else '') + f'>{text}{children}</sawx:expr>'


def report(formula='&quot;Invoice&quot;.&quot;Number&quot;', filters='', extra=''):
    return (f'<saw:report xmlns:saw="{c.SAW_NS}" xmlns:sawx="{c.SAWX_NS}" '
            f'xmlns:xsi="{c.XSI_NS}" name="Synthetic"><saw:criteria subjectArea="Synthetic Real Time">'
            '<saw:columns><saw:column columnID="c1"><saw:columnFormula>'
            + expr('sawx:sqlExpression', formula)
            + '</saw:columnFormula><saw:columnHeading><saw:caption><saw:text>Invoice / number</saw:text>'
            '</saw:caption></saw:columnHeading></saw:column></saw:columns>'
            + (f'<saw:filter>{filters}</saw:filter>' if filters else '')
            + extra + '</saw:criteria></saw:report>')


def analysis(filters='', formula='&quot;Invoice&quot;.&quot;Number&quot;', extra=''):
    return c.extract_report(report(formula, filters, extra), 0)


def mapping(table='Invoice', column='Number', obj='AP_INVOICES_ALL', dbcol='INVOICE_NUM', subject='Synthetic Real Time'):
    return dict(SUBJECT_AREA=subject, PRESENTATION_TABLE=table, PRESENTATION_COLUMN=column,
                DATABASE_OBJECT=obj, DATABASE_COLUMN=dbcol, workbook_row='2')


def comparison(value, op='equal', column='Number', kind='xsd:string'):
    return expr('sawx:comparison', op=op, children=expr('sawx:sqlExpression', f'"Invoice"."{column}"') + expr(kind, value))


def workbook(path):
    headers = ['SUBJECT_AREA', 'PRESENTATION_TABLE', 'PRESENTATION_COLUMN', 'DATABASE_OBJECT', 'DATABASE_COLUMN']
    rows = [headers, [mapping()[key] for key in headers]]
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i, row in enumerate(rows, 1):
        sheet += f'<row r="{i}">' + ''.join(f'<c r="{chr(65+j)}{i}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for j, value in enumerate(row)) + '</row>'
    sheet += '</sheetData></worksheet>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="OTBI Subject Areas" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', sheet)


class ConversionTests(unittest.TestCase):
    def test_literal_whitespace_preserved(self):
        a = analysis(comparison('  leading  and   internal '))
        self.assertIn("'  leading  and   internal '", a['filter']['explicit_sql'])

    def test_parameterized_like_is_not_dropped(self):
        a = analysis(expr('sawx:list', op='contains', children=expr('sawx:sqlExpression', '"Invoice"."Number"') + expr('xsd:string', "O'Brien")))
        self.assertIn("LIKE '%O''Brien%'", c.logical_sql(a, True, []))

    def test_numeric_literal_and_string_identifier_types(self):
        a = analysis(comparison('0012'))
        self.assertEqual(c.collect_parameters(a, a['subject_area'], [mapping()])[0]['type'], 'text')
        b = analysis(comparison('12.5', kind='xsd:decimal'))
        self.assertIn('= 12.5', b['filter']['explicit_sql'])

    def test_two_bounds_get_two_parameters(self):
        a = analysis(expr('sawx:logical', op='and', children=comparison('10', 'greaterOrEqual') + comparison('20', 'lessOrEqual')))
        p = c.collect_parameters(a, a['subject_area'], [mapping()])
        self.assertEqual(len(p), 2)
        self.assertEqual(len({x['name'] for x in p}), 2)
        sql = c.logical_sql(a, True, p)
        for x in p:
            self.assertIn(':'+x['name'], sql)

    def test_multi_select_uses_bind(self):
        a = analysis(expr('sawx:list', op='notIn', children=expr('sawx:sqlExpression', '"Invoice"."Number"') + expr('xsd:string', 'A') + expr('xsd:string', 'B')))
        p = c.collect_parameters(a, a['subject_area'], [mapping()])
        sql = c.logical_sql(a, True, p)
        self.assertIn('NOT IN (:P_', sql)
        self.assertNotIn('&P_', sql)

    def test_saved_filter_not_silently_ignored(self):
        with self.assertRaises(c.ConversionError):
            analysis(expr('sawx:savedFilter'))

    def test_unknown_filter_not_rendered_as_text(self):
        with self.assertRaises(c.ConversionError):
            analysis(expr('sawx:unknownOperator', 'x'))

    def test_unmapped_filter_rejected(self):
        a = analysis(comparison('x', column='Unmapped'))
        with self.assertRaises(c.ConversionError):
            c.physical_sql(a, a['subject_area'], [mapping()], [], False)

    def test_unmapped_formula_operand_rejected(self):
        a = analysis(formula='"Invoice"."Unmapped" + "Invoice"."Number"')
        with self.assertRaises(c.ConversionError):
            c.physical_sql(a, a['subject_area'], [mapping()], [], False)

    def test_string_literal_is_not_mapped(self):
        text = '''CASE WHEN "Invoice"."Number" = '"Invoice"."Number"' THEN 1 ELSE 0 END'''
        result, _ = c.substitute_physical_references(text, 'Synthetic Real Time', [mapping()], {})
        self.assertIn("'\"Invoice\".\"Number\"'", result)

    def test_qualified_reference_uses_named_subject(self):
        m = mapping(subject='Other Real Time')
        result, _ = c.substitute_physical_references('"Other Real Time"."Invoice"."Number"', 'Synthetic Real Time', [m], {})
        self.assertEqual(result, 'AP_INVOICES_ALL.INVOICE_NUM')

    def test_ambiguous_mapping_rejected(self):
        with self.assertRaises(c.ConversionError):
            c.physical_sql(analysis(), 'Synthetic Real Time', [mapping(), mapping(obj='OTHER')], [], False)

    def test_native_sort_and_exact_heading(self):
        a = analysis(extra='<saw:columnOrder><saw:columnOrderRef columnID="c1" direction="ascending"/></saw:columnOrder>')
        sql = c.logical_sql(a, False, [])
        self.assertIn('"Invoice / number"', sql)
        self.assertIn(' ASC', sql)
        self.assertNotIn(' ASCENDING', sql)

    def test_multi_table_scaffold_returns_no_rows(self):
        a = analysis(comparison('x', column='Supplier'))
        sql, _ = c.physical_sql(a, a['subject_area'], [mapping(), mapping(column='Supplier', obj='SUPPLIERS', dbcol='NAME')], [], False)
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript("CREATE TABLE AP_INVOICES_ALL(INVOICE_NUM TEXT); INSERT INTO AP_INVOICES_ALL VALUES('1'),('2'); CREATE TABLE SUPPLIERS(NAME TEXT); INSERT INTO SUPPLIERS VALUES('x'),('x');")
        self.assertEqual(db.execute(sql).fetchall(), [])

    def test_logical_only_function_rejected(self):
        for fn in ('IFNULL', 'FILTER', 'DESCRIPTOR_IDOF', 'AGO', 'EVALUATE'):
            with self.subTest(fn=fn), self.assertRaises(c.ConversionError):
                c.physical_sql(analysis(formula=f'{fn}("Invoice"."Number")'), 'Synthetic Real Time', [mapping()], [], False)

    def test_explicit_aggregate_requires_semantic_translation(self):
        with self.assertRaises(c.ConversionError):
            c.physical_sql(analysis(formula='SUM("Invoice"."Number")'), 'Synthetic Real Time', [mapping()], [], False)

    def test_catalog_multiple_streams(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'test.catalog'
            path.write_bytes(b'header' + zlib.compress(report().encode()) + b'trailer' + zlib.compress(report().encode()))
            self.assertEqual(len(c.extract_catalog(path)), 2)

    def test_binary_wrapper_around_utf8_xml(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'binary.catalog'
            xml = report(filters=comparison('Caf\u00e9'))
            path.write_bytes(zlib.compress(b'\x00\xc5\xffmetadata' + xml.encode('utf-8') + b'\xfe\x00'))
            a = c.extract_catalog(path)[0]
            self.assertIn('Caf\u00e9', a['filter']['explicit_sql'])

    def test_invalid_bytes_inside_xml_do_not_change_silently(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'invalid.catalog'
            path.write_bytes(zlib.compress(report(filters=comparison('X')).encode().replace(b'>X<', b'>\xff<')))
            with self.assertRaises(c.ConversionError):
                c.extract_catalog(path)

    def test_inspect_without_workbook(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'test.catalog'
            path.write_bytes(zlib.compress(report().encode()))
            r = subprocess.run([sys.executable, '-B', str(HELPER), str(path), '--inspect'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertEqual(data['analyses'][0]['subject_area'], 'Synthetic Real Time')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['test.catalog'])

    def test_cli_scaffolds_and_provenance(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            path = root/'test with spaces.catalog'
            path.write_bytes(zlib.compress(report(filters=comparison('0012')).encode()))
            wb = root/'mapping.xlsx'
            workbook(wb)
            cmd = [sys.executable, '-B', str(HELPER), str(path), '--mapping-workbook', str(wb), '--output-dir', str(root/'out')]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            summary = json.loads(r.stdout)
            self.assertEqual(summary['conversion_status'], 'blocked_scaffold')
            outputs = [Path(p) for p in summary['outputs']]
            self.assertTrue(all(p.exists() for p in outputs))
            manifest = json.loads(next(p for p in outputs if p.name.endswith('-manifest.json')).read_text())
            self.assertEqual(manifest['source_catalog']['sha256'], c.sha256_file(path))
            self.assertEqual(manifest['validation']['otbi_reconciliation'], 'not_run')
            self.assertTrue(any(p.name.endswith('-validation.md') for p in outputs))
            for p in outputs:
                if p.suffix == '.sql' and ('physical-' in p.name or p.parent.name.endswith('-parameters')):
                    self.assertIn('1 = 0', p.read_text())
            before = {p: p.read_bytes() for p in outputs}
            again = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(again.returncode, 1)
            self.assertIn('already exist', again.stderr)
            self.assertEqual(before, {p: p.read_bytes() for p in outputs})

    def test_cli_selects_before_requiring_other_analysis_runtime(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            catalog = root/'multiple.catalog'
            other = report(filters=expr('sawx:eval', 'unselected_prompt'))
            catalog.write_bytes(zlib.compress(report().encode()) + zlib.compress(other.encode()))
            wb = root/'mapping.xlsx'
            workbook(wb)
            cmd = [sys.executable, '-B', str(HELPER), str(catalog), '--mapping-workbook', str(wb), '--output-dir', str(root/'out')]
            missing = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertIn('multiple analyses', missing.stderr)
            chosen = subprocess.run(cmd + ['--analysis-index', '1'], capture_output=True, text=True)
            self.assertEqual(chosen.returncode, 0, chosen.stderr)

    def test_cli_rejects_zero_index_and_ambiguous_name(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            catalog = root/'multiple.catalog'
            catalog.write_bytes(zlib.compress((report()+report()).encode()))
            wb = root/'mapping.xlsx'
            workbook(wb)
            cmd = [sys.executable, '-B', str(HELPER), str(catalog), '--mapping-workbook', str(wb)]
            for selection in (['--analysis-index', '0'], ['--analysis-name', 'Synthetic']):
                r = subprocess.run(cmd + selection, capture_output=True, text=True)
                self.assertEqual(r.returncode, 1, r.stdout)

    def test_inspection_preserves_runtime_and_raw_formulas(self):
        f = expr('sawx:list', op='in', children=expr('sawx:sqlExpression', '"Invoice"."Number"') + expr('sawx:eval', 'period_prompt'))
        a = c.extract_report(report(formula='IFNULL(FILTER("Invoice"."Number" USING "Invoice"."Number" = \'  A  \'),0)', filters=f), 0, inspect_only=True)
        self.assertTrue(a['inspection_blockers'])
        self.assertIn("'  A  '", a['columns'][0]['expression'])
        self.assertIn('period_prompt', a['raw_report_xml'])
        with self.assertRaises(c.ConversionError):
            c.extract_report(report(filters=f), 0)

    def test_combined_criteria_preserved_for_manual_translation(self):
        xml = report().replace('<saw:columns>', '<saw:combined><saw:columns>').replace('</saw:columns>', '</saw:columns></saw:combined>')
        a = c.extract_report(xml, 0, inspect_only=True)
        self.assertIn('combined', a['raw_report_xml'])
        self.assertTrue(a['inspection_blockers'])
        with self.assertRaises(c.ConversionError):
            c.extract_report(xml, 0)

    def test_mixed_list_types_require_review(self):
        f = expr('sawx:list', op='in', children=expr('sawx:sqlExpression', '"Invoice"."Number"') + expr('xsd:string', '1') + expr('xsd:integer', '2'))
        a = analysis(f)
        with self.assertRaises(c.ConversionError):
            c.collect_parameters(a, a['subject_area'], [mapping()])

    def test_supported_scalar_expression_still_maps_every_operand(self):
        a = analysis(formula='NVL("Invoice"."Number", 0) + "Invoice"."Tax"')
        sql, used = c.physical_sql(a, a['subject_area'], [mapping(), mapping(column='Tax', dbcol='TAX_AMOUNT')], [], False)
        self.assertIn('NVL(AP_INVOICES_ALL.INVOICE_NUM, 0) + AP_INVOICES_ALL.TAX_AMOUNT', sql)
        self.assertEqual(len(used), 2)

    def test_null_and_between_filters_survive_parameterization(self):
        for f, expected in [
            (expr('sawx:unary', op='isNull', children=expr('sawx:sqlExpression', '"Invoice"."Number"')), 'IS NULL'),
            (expr('sawx:between', op='between', children=expr('sawx:sqlExpression', '"Invoice"."Number"') + expr('xsd:integer', '1') + expr('xsd:integer', '9')), 'BETWEEN 1 AND 9'),
        ]:
            a = analysis(f)
            self.assertIn(expected, c.logical_sql(a, True, []))

    def test_invalid_typed_literal_rejected(self):
        for kind, value in [('xsd:date', '2026-02-31'), ('xsd:decimal', '1 OR 1=1'), ('xsd:dateTime', '2026-01-01T01:00:00Z')]:
            with self.subTest(kind=kind), self.assertRaises(c.ConversionError):
                analysis(comparison(value, kind=kind))

    def test_complete_report_in_truncated_stream_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)/'test.catalog'
            path.write_bytes(zlib.compress(report().encode())[:-4])
            with self.assertRaises(c.ConversionError):
                c.extract_catalog(path)

    def test_no_partial_outputs_on_missing_mapping(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            catalog = root/'test.catalog'
            catalog.write_bytes(zlib.compress(report(filters=comparison('x', column='Unmapped')).encode()))
            wb = root/'mapping.xlsx'
            workbook(wb)
            with self.assertRaises(c.ConversionError):
                c.write_outputs(c.extract_catalog(catalog)[0], catalog, wb, c.read_mapping_workbook(wb), root/'out', 'test', False)
            self.assertFalse((root/'out').exists())

    def test_sort_only_mapping_and_duplicate_lineage_rows(self):
        a = analysis()
        a['sorts'] = [dict(expression='"Invoice"."Supplier"', direction='descending')]
        with self.assertRaises(c.ConversionError):
            c.physical_sql(a, a['subject_area'], [mapping()], [], False)
        sql, _ = c.physical_sql(a, a['subject_area'], [mapping(), mapping(), mapping(column='Supplier', obj='SUPPLIERS', dbcol='NAME')], [], False)
        self.assertIn('SUPPLIERS.NAME DESC', sql)
        self.assertIn('FROM AP_INVOICES_ALL, SUPPLIERS', sql)

    def test_conditional_measures_stay_separate_in_reference_example(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript("CREATE TABLE fact(dept TEXT, category TEXT, cost DECIMAL); INSERT INTO fact VALUES('A','travel',10),('A','salary',20),('B','salary',30);")
        rows = db.execute("SELECT dept, COALESCE(SUM(CASE WHEN category='travel' THEN cost END),0), SUM(cost) FROM fact GROUP BY dept ORDER BY dept").fetchall()
        self.assertEqual(rows, [('A',10,30), ('B',0,30)])
        # Moving a measure-only condition to WHERE incorrectly removes B and changes Total.
        wrong = db.execute("SELECT dept,SUM(cost) FROM fact WHERE category='travel' GROUP BY dept").fetchall()
        self.assertNotEqual(wrong, [(r[0],r[2]) for r in rows])


if __name__ == '__main__':
    unittest.main(verbosity=2)
