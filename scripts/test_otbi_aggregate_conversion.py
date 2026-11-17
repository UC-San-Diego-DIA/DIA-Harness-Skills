"""Offline behavior checks for prompt resolution and additive OTBI compilation."""
from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import json
import zlib
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/dia-otbi-to-bipublisher-sql/scripts'))
import aggregate_expressions as expressions
import compile_reviewed_conversion as compiler
import convert_otbi_catalog as source

ORG = '"Project"."Organization"'
COST = '"Measures"."Cost"'
TYPE = '"Resource"."Name"'
TASK = '"Task"."Number"'
PERIOD = '"Calendar"."Period"'


def fixture(totals=False, runtime=True):
    formulas = [ORG, COST,
                f'IFNULL(FILTER({COST} USING {TYPE} IN (\'A\',\'B\')),0)-IFNULL(FILTER({COST} USING {TASK} LIKE \'4%\'),0)',
                f'IFNULL(FILTER({COST} USING DESCRIPTOR_IDOF({TASK})=99),0)']
    columns = ''.join(f'<saw:column columnID="c{i}"><saw:columnFormula><sawx:expr xsi:type="sawx:sqlExpression">{escape(x)}</sawx:expr></saw:columnFormula>' + ('<saw:displayFormat><saw:formatSpec visibility="hidden"/></saw:displayFormat>' if i == 1 else '') + '</saw:column>' for i, x in enumerate(formulas))
    period_value = '<sawx:expr xsi:type="sawx:eval" default="noData">p_period</sawx:expr>' if runtime else '<sawx:expr xsi:type="xsd:string">P1</sawx:expr>'
    xml = f'''<saw:report xmlns:saw="{source.SAW_NS}" xmlns:sawx="{source.SAWX_NS}" xmlns:xsi="{source.XSI_NS}"><saw:criteria subjectArea="Synthetic Costs"><saw:columns>{columns}</saw:columns><saw:filter><sawx:expr xsi:type="sawx:list" op="in"><sawx:expr xsi:type="sawx:sqlExpression">{escape(PERIOD)}</sawx:expr>{period_value}</sawx:expr></saw:filter></saw:criteria><saw:views><saw:view xsi:type="saw:tableView" name="tableView!1"><saw:edges><saw:edge axis="row">{('<saw:displayGrandTotals><saw:displayGrandTotal grandTotalPosition="after"/></saw:displayGrandTotals>' if totals else '')}<saw:edgeLayers><saw:edgeLayer columnID="c0"/><saw:edgeLayer columnID="c3"/><saw:edgeLayer columnID="c2"/><saw:edgeLayer columnID="c1"/></saw:edgeLayers></saw:edge></saw:edges></saw:view></saw:views></saw:report>'''
    analysis = source.extract_report(xml, 0, inspect_only=True)
    definitions = [(ORG,'ORG','string'),(COST,'COST','decimal'),(TYPE,'RESOURCE_NAME','string'),(TASK,'TASK_NUM','string'),(PERIOD,'PERIOD','string')]
    fields, mappings = [], []
    for ref, col, dtype in definitions:
        m = source.PRESENTATION_REF.fullmatch(ref)
        b = dict(presentation_ref=ref,table_alias='f',database_column=col,data_type=dtype,semantic_role='measure' if ref==COST else 'attribute', evidence=['schema'])
        if ref == COST:
            b.update(aggregation='SUM',input_grain='one fact row',currency='synthetic units',row_selection='all rows in criteria scope')
        if ref == TASK:
            b['descriptor'] = dict(table_alias='f',database_column='TASK_ID',data_type='integer',lineage='Synthetic key distinct from display number',evidence=['schema'])
        fields.append(b)
        mappings.append(dict(SUBJECT_AREA='Synthetic Costs',PRESENTATION_TABLE=m.group('table'),PRESENTATION_COLUMN=m.group('column'),DATABASE_OBJECT='FACT',DATABASE_COLUMN=col,workbook_row=str(len(mappings)+2)))
    plan = dict(schema_version=2,subject_area='Synthetic Costs',grain='organization',comparison_scope='synthetic P1',reviewed_by='fixture',reviewed_at='2026-11-12',sources={'schema':dict(title='Synthetic schema',location='test fixture'),'user':dict(title='Confirmed runtime selection',location='synthetic user request')},root_table=dict(alias='f',object='FACT',evidence=['schema']),joins=[],field_mappings=fields,required_projected_refs=[ORG],fact_grain=dict(keys=['f.ID'],evidence=['schema']),runtime_values={'p_period':dict(data_type='string',values=['P1'],evidence=['user'])} if runtime else {},output_bindings=[dict(column_id=f'c{i}',output_name=name) for i,name in enumerate(['ORG','TOTAL_COST','NET_COST','KEY_COST'])])
    plan['physical_scope'] = dict(status='reviewed',restrictions=[],evidence=['schema'])
    if totals:
        plan['grand_total'] = dict(method='recompute_source_formulas',evidence=['schema'])
    return analysis, dict(mappings=mappings), plan


def database():
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE FACT(ID INTEGER PRIMARY KEY, ORG TEXT, COST NUMERIC, RESOURCE_NAME TEXT, TASK_NUM TEXT, TASK_ID INTEGER, PERIOD TEXT);
INSERT INTO FACT VALUES(1,'X',10,'A','1',99,'P1'),(2,'X',10,'A','4',88,'P1'),(3,'X',-3,'Z','4',99,'P1'),(4,'Y',7,'B','7',1,'P1'),(5,'Y',999,'A','1',99,'P2'),(6,'Z',NULL,'Z','9',2,'P1');''')
    return db


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.a,self.w,self.p = fixture()
        _,_,_,bindings = compiler.reviewed_bindings(self.a,self.w,self.p)
        self.t = expressions.Translator('Synthetic Costs', list(bindings.values()))

    def evaluate(self, expression, org='X'):
        db = database(); self.addCleanup(db.close)
        sql = self.t.compile(expression).sql
        return db.execute('SELECT '+sql+' FROM FACT f WHERE f.ORG=? AND f.PERIOD=?',(org,'P1')).fetchone()[0]

    def test_filtered_subtraction_preserves_overlapping_rows_and_duplicate_amounts(self):
        # A sum=20, task4 sum=7. A row belongs to both and must cancel once.
        self.assertEqual(self.evaluate(self.a['columns'][2]['expression']),13)

    def test_descriptor_uses_key_not_display_number(self):
        self.assertEqual(self.evaluate(self.a['columns'][3]['expression']),7)

    def test_missing_descriptor_lineage_rejected(self):
        self.t.binding(TASK).pop('descriptor')
        with self.assertRaisesRegex(source.ConversionError,'Descriptor key'):
            self.t.compile(f'DESCRIPTOR_IDOF({TASK})=99')

    def test_null_fallback_stays_after_aggregation(self):
        self.assertEqual(self.evaluate(f'IFNULL(FILTER({COST} USING {TYPE}=\'missing\'),0)'),0)
        self.assertIsNone(self.evaluate(f'FILTER({COST} USING {TYPE}=\'missing\')'))

    def test_qualified_and_unqualified_primary_area_match(self):
        self.assertEqual(self.evaluate('"Synthetic Costs".'+COST),17)

    def test_other_subject_area_does_not_fall_back(self):
        with self.assertRaisesRegex(source.ConversionError,'No reviewed mapping'):
            self.t.compile('"Other".'+COST)

    def test_literals_preserve_apostrophes_whitespace_and_apparent_missing_comma(self):
        for literal in ["'A''B'", "'  padded'", "'123''456'"]:
            self.assertIn(literal,self.t.compile(f'FILTER({COST} USING {TYPE}={literal})').sql)

    def test_arithmetic_precedence_and_safe_ratio(self):
        self.assertEqual(self.evaluate(f'IFNULL({COST},0)+2*3'),23)
        self.assertEqual(self.evaluate(f'{COST}/NULLIF({COST},0)'),1)
        self.assertIsNone(self.evaluate(f'{COST}/NULLIF({COST},0)','Z'))

    def test_measure_in_predicate_rejected(self):
        with self.assertRaisesRegex(source.ConversionError,'row-level'):
            self.t.compile(f'FILTER({COST} USING {COST}>0)')

    def test_nested_aggregate_and_unknown_function_rejected(self):
        for bad in [f'SUM({COST})', f'FILTER(IFNULL({COST},0) USING {TYPE}=\'A\')',f'AVG({COST})']:
            with self.assertRaises(source.ConversionError):self.t.compile(bad)

    def test_mixed_aggregate_and_row_value_rejected(self):
        with self.assertRaisesRegex(source.ConversionError,'Mixed row and aggregate'):
            self.t.compile(COST+' + DESCRIPTOR_IDOF('+TASK+')')

    def test_unknown_tokens_and_injection_fail_closed(self):
        for bad in [COST+'; SELECT 1',COST+' --x', COST+' /*x*/',"'unclosed",'@{p}{0}', f'FILTER({COST} USING {TYPE} IN ())']:
            with self.assertRaises(source.ConversionError):self.t.compile(bad)

    def test_runtime_overrides_default_without_modifying_source(self):
        before = copy.deepcopy(self.a)
        sql, record = expressions.resolve_runtime_filter(self.a,self.p['runtime_values'],self.p['sources'])
        self.assertIn("'P1'",sql);self.assertNotIn('noData',sql)
        self.assertEqual(record[0]['saved_default'],'noData');self.assertEqual(before,self.a)

    def test_multiple_runtime_values_are_separate_escaped_literals(self):
        self.p['runtime_values']['p_period']['values']=['P1',"P'2"]
        sql,_=expressions.resolve_runtime_filter(self.a,self.p['runtime_values'],self.p['sources'])
        self.assertIn("IN ('P1', 'P''2')",sql)

    def test_unknown_missing_empty_or_unreviewed_runtime_rejected(self):
        for runtime in [{},{'other':dict(data_type='string',values=['P1'],evidence=['user'])},{'p_period':dict(data_type='string',values=[],evidence=['user'])},{'p_period':dict(data_type='string',values=['P1'],evidence=[])}]:
            with self.assertRaises(source.ConversionError):expressions.resolve_runtime_filter(self.a,runtime,self.p['sources'])

    def test_compiled_query_matches_independent_grouped_values_and_view_order(self):
        sql,out=compiler.compile_analysis(self.a,self.w,self.p)
        db=database();self.addCleanup(db.close)
        self.assertEqual(sorted(db.execute(sql).fetchall()),[('X',7,13),('Y',0,7),('Z',0,0)])
        self.assertEqual([o['name'] for o in out],['ORG','KEY_COST','NET_COST'])
        self.assertNotIn('noData',sql)
        self.assertNotIn('SUM(DISTINCT',sql)
        self.assertEqual(len(out[0]['runtime_resolutions']),1)

    def test_row_policy_keeps_required_measure_aggregation(self):
        self.p['row_policy']='aggregate_grain'
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        db=database(); self.addCleanup(db.close)
        self.assertEqual(sorted(db.execute(sql).fetchall()),[('X',7,13),('Y',0,7),('Z',0,0)])
        for policy in ['physical_rows','otbi_distinct']:
            self.p['row_policy']=policy
            with self.assertRaisesRegex(compiler.Error,'row_policy'):
                compiler.compile_analysis(self.a,self.w,self.p)

    def test_total_stage_recomputes_source_formula_and_hidden_cost_is_retained(self):
        a,w,p=fixture(totals=True)
        sql,out=compiler.compile_analysis(a,w,p)
        self.assertIn('GROUPING SETS ((f.ORG), ())',sql)
        self.assertIn('SUM(f.COST) AS TOTAL_COST',sql)
        self.assertIn("THEN 'Grand Total'",sql)
        self.assertIn('ORDER BY OTBI_TOTAL_ROW ASC',sql)
        self.assertEqual(len(out),3)

    def test_no_measure_definition_no_candidate(self):
        for key in ['aggregation','currency','input_grain','row_selection']:
            p=copy.deepcopy(self.p);p['field_mappings'][1].pop(key)
            with self.assertRaises(source.ConversionError):compiler.compile_analysis(self.a,self.w,p)

    def test_multiplying_join_and_missing_fact_key_rejected(self):
        self.p['joins']=[dict(alias='x',object='DETAIL',kind='INNER',cardinality='one-to-many',keys=[['x.ID','f.ID']],evidence=['schema'])]
        with self.assertRaisesRegex(source.ConversionError,'multiplying'):compiler.compile_analysis(self.a,self.w,self.p)
        self.p['joins']=[];self.p['fact_grain']['keys']=[]
        with self.assertRaisesRegex(source.ConversionError,'root fact key'):compiler.compile_analysis(self.a,self.w,self.p)

    def test_unmapped_cost_choice_cannot_be_forced(self):
        self.p['field_mappings'][1]['database_column']='UNKNOWN_AMOUNT'
        with self.assertRaisesRegex(source.ConversionError,'lineage workbook'):compiler.compile_analysis(self.a,self.w,self.p)

    def test_external_runtime_sort_and_heading_need_evidence(self):
        self.p['result_sort']=[dict(column_id='c0',direction='ascending',nulls='LAST',evidence=['user'])]
        self.p['output_bindings'][0].update(heading='Display organization',evidence=['user'])
        sql,out=compiler.compile_analysis(self.a,self.w,self.p)
        self.assertIn('ORG ASC NULLS LAST',sql);self.assertEqual(out[0]['heading'],'Display organization')
        self.p['result_sort'][0].pop('evidence')
        with self.assertRaises(source.ConversionError):compiler.compile_analysis(self.a,self.w,self.p)

    def test_selected_view_cannot_drop_a_source_column(self):
        root=ET.fromstring(self.a['raw_report_xml'])
        for parent in root.iter():
            for child in list(parent):
                if source.local_name(child.tag)=='edgeLayer' and child.get('columnID')=='c1':parent.remove(child)
        self.a['raw_report_xml']=ET.tostring(root,encoding='unicode')
        with self.assertRaisesRegex(source.ConversionError,'every source column'):compiler.compile_analysis(self.a,self.w,self.p)

    def test_physical_restrictions_are_applied_with_typed_literals(self):
        self.p['physical_scope']['restrictions'] = [dict(table_alias='f',database_column='ORG',operator='=',data_type='string',values=['Y'],evidence=['schema'])]
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        db=database();self.addCleanup(db.close)
        self.assertEqual(db.execute(sql).fetchall(),[('Y',0,7)])

    def test_missing_scope_or_total_stage_review_blocks_compilation(self):
        self.p.pop('physical_scope')
        with self.assertRaises(source.ConversionError):compiler.compile_analysis(self.a,self.w,self.p)
        a,w,p=fixture(totals=True);p.pop('grand_total')
        with self.assertRaises(source.ConversionError):compiler.compile_analysis(a,w,p)

    def test_full_catalog_prompt_compilation_and_visible_model_packaging(self):
        import test_otbi_reviewed_conversion as base
        a,w,p=fixture(totals=True)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            directory=Path(tmp)
            catalog=directory/'Synthetic.catalog';catalog.write_bytes(zlib.compress(a['raw_report_xml'].encode()))
            workbook=directory/'lineage.xlsx';base.write_workbook(workbook,w['mappings'])
            template=directory/'Template.xdm.catalog';template.write_bytes(base.template())
            p.update(source_catalog_sha256=source.sha256_file(catalog),mapping_workbook_sha256=source.sha256_file(workbook),template_model_sha256=source.sha256_file(template),data_source='SyntheticDB')
            review=directory/'review.json';review.write_text(json.dumps(p),encoding='utf-8')
            args=SimpleNamespace(catalog=catalog,mapping_workbook=workbook,review_plan=review,template_model=template,analysis_index=None,output_dir=directory/'output',base_name='Synthetic')
            result=compiler.run(args)
            self.assertEqual(result['conversion_status'],'CANDIDATE_NOT_EXECUTED')
            self.assertEqual(result['column_count'],3)
            manifest=json.loads((args.output_dir/'Synthetic-manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['validation']['oracle_execution'],'not_run')
            self.assertIn('noData',manifest['analysis']['raw_report_xml'])
            self.assertEqual(manifest['outputs'][0]['runtime_resolutions'][0]['values'],['P1'])
            _,_,_,model=compiler.read_model_template((args.output_dir/'Synthetic.xdm.catalog').read_bytes())
            self.assertEqual([e.get('name') for e in model.findall('.//{'+compiler.MODEL_NS+'}element')],['ORG','KEY_COST','NET_COST'])
            self.assertNotIn('noData',(args.output_dir/'Synthetic.sql').read_text(encoding='utf-8'))
            with self.assertRaisesRegex(source.ConversionError,'already exists'):compiler.run(args)


if __name__=='__main__':
    unittest.main(verbosity=2)
