"""Executable conversion regressions using synthetic data and public Oracle object names."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zlib
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'skills/dia-otbi-to-bipublisher-sql/scripts'
sys.path.insert(0, str(FOLDER))
import compile_reviewed_conversion as compiler
import convert_otbi_catalog as source

spec = importlib.util.spec_from_file_location('existing_tests', ROOT/'scripts/test_otbi_conversion.py')
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)

FIELDS = [
    ('Supplier', 'Supplier Name', 'hp', 'HZ_PARTIES', 'PARTY_NAME', 'SUPPLIER_NAME', 'string'),
    ('Supplier', 'Supplier Number', 'ps', 'POZ_SUPPLIERS', 'SEGMENT1', 'SUPPLIER_NUMBER', 'string'),
    ('- General Information', 'Invoice Date', 'ai', 'AP_INVOICES_ALL', 'INVOICE_DATE', 'INVOICE_DATE', 'date'),
    ('- General Information', 'Invoice Number', 'ai', 'AP_INVOICES_ALL', 'INVOICE_NUM', 'INVOICE_NUMBER', 'string'),
    ('- Invoice Line Details - General Information', 'Line Number', 'ail', 'AP_INVOICE_LINES_ALL', 'LINE_NUMBER', 'INVOICE_LINE_NUMBER', 'integer'),
    ('- Invoice Distribution Details - General Information', 'Distribution Line Number', 'aid', 'AP_INVOICE_DISTRIBUTIONS_ALL', 'DISTRIBUTION_LINE_NUMBER', 'INVOICE_DISTRIBUTION_NUMBER', 'integer'),
]


def inputs(order=None, predicate=''):
    order = list(range(6)) if order is None else order
    columns = ''.join('<saw:column columnID="c'+str(i)+'"><saw:columnFormula>'+existing.expr('sawx:sqlExpression', escape(f'"{FIELDS[i][0]}"."{FIELDS[i][1]}"'))+'</saw:columnFormula></saw:column>' for i in order)
    xml = f'<saw:report xmlns:saw="{source.SAW_NS}" xmlns:sawx="{source.SAWX_NS}" xmlns:xsi="{source.XSI_NS}"><saw:criteria subjectArea="Synthetic Invoices"><saw:columns>{columns}</saw:columns>' + (f'<saw:filter>{predicate}</saw:filter>' if predicate else '') + '</saw:criteria></saw:report>'
    mappings = [dict(SUBJECT_AREA='Synthetic Invoices', PRESENTATION_TABLE=t, PRESENTATION_COLUMN=c, DATABASE_OBJECT=obj, DATABASE_COLUMN=dbcol, workbook_row=str(i+2)) for i,(t,c,a,obj,dbcol,out,dtype) in enumerate(FIELDS)]
    # The wrong branch is deliberately first, as in a real multi-family lineage workbook.
    mappings.insert(0, {**mappings[0], 'DATABASE_OBJECT':'OTHER_SUPPLIERS', 'DATABASE_COLUMN':'NAME', 'workbook_row':'1'})
    return source.extract_report(xml, 0), dict(mappings=mappings, cover_text=[])


def plan():
    result = dict(schema_version=1, subject_area='Synthetic Invoices', grain='invoice distribution', comparison_scope='synthetic unfiltered reference', reviewed_by='offline fixture', reviewed_at='2026-11-12', sources={'schema':dict(title='Synthetic schema evidence', location='synthetic-fixture')}, root_table=dict(alias='ai', object='AP_INVOICES_ALL'), joins=[], field_mappings=[], required_projected_refs=[f'"{FIELDS[5][0]}"."{FIELDS[5][1]}"'], data_source='ApplicationDB_FSCM')
    for alias,obj,kind,keys,cardinality in [
        ('ail','AP_INVOICE_LINES_ALL','INNER',[['ail.INVOICE_ID','ai.INVOICE_ID']],'one-to-many'),
        ('aid','AP_INVOICE_DISTRIBUTIONS_ALL','INNER',[['aid.INVOICE_ID','ail.INVOICE_ID'],['aid.INVOICE_LINE_NUMBER','ail.LINE_NUMBER']],'one-to-many'),
        ('ps','POZ_SUPPLIERS','LEFT',[['ps.VENDOR_ID','ai.VENDOR_ID']],'many-to-one'),
        ('hp','HZ_PARTIES','LEFT',[['hp.PARTY_ID','ps.PARTY_ID']],'many-to-one'),
    ]:
        result['joins'].append(dict(alias=alias,object=obj,kind=kind,keys=keys,cardinality=cardinality,evidence=['schema']))
    for t,c,a,obj,col,out,dtype in FIELDS:
        result['field_mappings'].append(dict(presentation_ref=f'"{t}"."{c}"',table_alias=a,database_column=col,output_name=out,data_type=dtype,semantic_role='attribute',evidence=['schema']))
    return result


def template(sql='SELECT 1 AS OLD_COLUMN FROM DUAL'):
    ns=compiler.MODEL_NS
    xml=(f'<?xml version="1.0" encoding="utf-8"?><dataModel xmlns="{ns}" defaultDataSourceRef="WrongDefault"><dataSets><dataSet name="main" type="complex"><sql dataSourceRef="ApplicationDB_FSCM">{escape(sql)}</sql></dataSet></dataSets><output><group source="main" name="G_1"><element name="OLD_COLUMN"/></group></output><parameters/><lexicals/><eventTriggers/><bursting/><valueSets/><validations><validation>Y</validation></validations></dataModel>\n').encode()
    item=json.dumps(dict(ItemName='Synthetic.xdm',ItemType=1,ObjectSignature='',OriginalPath='/Synthetic/Synthetic.xdm')).encode()
    prefix=b'\x10\x00\x00\x00binary'+struct.pack('<I',len(item))+item+b'\x01\x00'
    return zlib.compress(prefix+struct.pack('<Q',len(xml))+xml+b'\x02\x00')


def database():
    db=sqlite3.connect(':memory:')
    db.executescript('''
CREATE TABLE AP_INVOICES_ALL(INVOICE_ID INTEGER PRIMARY KEY, VENDOR_ID INTEGER, INVOICE_NUM TEXT, INVOICE_DATE TEXT);
CREATE TABLE AP_INVOICE_LINES_ALL(INVOICE_ID INTEGER, LINE_NUMBER INTEGER, PRIMARY KEY(INVOICE_ID,LINE_NUMBER));
CREATE TABLE AP_INVOICE_DISTRIBUTIONS_ALL(INVOICE_DISTRIBUTION_ID INTEGER PRIMARY KEY, INVOICE_ID INTEGER, INVOICE_LINE_NUMBER INTEGER, DISTRIBUTION_LINE_NUMBER INTEGER);
CREATE TABLE POZ_SUPPLIERS(VENDOR_ID INTEGER PRIMARY KEY, SEGMENT1 TEXT, PARTY_ID INTEGER);
CREATE TABLE HZ_PARTIES(PARTY_ID INTEGER PRIMARY KEY, PARTY_NAME TEXT);
INSERT INTO HZ_PARTIES VALUES(1,'Synthetic Supplier');
INSERT INTO POZ_SUPPLIERS VALUES(100,'0012',1),(200,'NO_PARTY',999);
INSERT INTO AP_INVOICES_ALL VALUES(1,100,'A','2026-01-01'),(2,100,'A','2026-01-01'),(3,999,'NO_VENDOR','2026-01-02'),(4,200,'NO_PARTY','2026-01-03'),(5,100,'NO_LINE','2026-01-04');
INSERT INTO AP_INVOICE_LINES_ALL VALUES(1,1),(1,2),(2,1),(3,1),(4,1),(4,2);
INSERT INTO AP_INVOICE_DISTRIBUTIONS_ALL VALUES(1,1,1,1),(2,1,1,2),(3,1,2,1),(4,2,1,1),(5,3,1,1),(6,4,1,1);
''')
    return db


def write_workbook(path, mappings):
    headers=['SUBJECT_AREA','PRESENTATION_TABLE','PRESENTATION_COLUMN','DATABASE_OBJECT','DATABASE_COLUMN']
    sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i,row in enumerate([headers]+[[m.get(key,'') for key in headers] for m in mappings],1):
        sheet+=f'<row r="{i}">'+''.join(f'<c r="{chr(65+j)}{i}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for j,value in enumerate(row))+'</row>'
    sheet+='</sheetData></worksheet>'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="OTBI Subject Areas" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',sheet)


# Independent query contract for the input example, in source OTBI column order.
REFERENCE = '''SELECT hp.PARTY_NAME, ps.SEGMENT1, ai.INVOICE_DATE, ai.INVOICE_NUM, ail.LINE_NUMBER, aid.DISTRIBUTION_LINE_NUMBER
FROM AP_INVOICES_ALL ai
JOIN AP_INVOICE_LINES_ALL ail ON ail.INVOICE_ID=ai.INVOICE_ID
JOIN AP_INVOICE_DISTRIBUTIONS_ALL aid ON aid.INVOICE_ID=ail.INVOICE_ID AND aid.INVOICE_LINE_NUMBER=ail.LINE_NUMBER
LEFT JOIN POZ_SUPPLIERS ps ON ps.VENDOR_ID=ai.VENDOR_ID
LEFT JOIN HZ_PARTIES hp ON hp.PARTY_ID=ps.PARTY_ID'''


class ReviewedConversionTests(unittest.TestCase):
    def setUp(self):
        self.a,self.w=inputs()
        self.p=plan()

    def test_default_preserves_physical_row_multiplicities(self):
        sql,out=compiler.compile_analysis(self.a,self.w,self.p)
        db=database(); self.addCleanup(db.close)
        actual=db.execute(sql).fetchall()
        reference=db.execute(REFERENCE).fetchall()
        self.assertEqual(Counter(actual),Counter(reference))
        self.assertEqual(len(actual),6)
        self.assertEqual(len(reference),6)
        self.assertEqual(len(set(actual)),5)
        self.assertNotIn('1 = 0',sql)
        self.assertNotIn('VERIFY',sql)
        self.assertNotIn('ORDER BY',sql)
        self.assertEqual([x['name'] for x in out],[x[5] for x in FIELDS])

    def test_explicit_otbi_distinct_collapses_projected_tuples(self):
        self.p['row_policy']='otbi_distinct'
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        db=database(); self.addCleanup(db.close)
        actual=db.execute(sql).fetchall()
        reference=db.execute(REFERENCE).fetchall()
        self.assertEqual(Counter(actual),Counter(set(reference)))
        self.assertEqual(len(actual),5)
        self.assertEqual(len(reference),6)

    def test_unknown_row_policy_is_rejected(self):
        for policy in ['DISTINCT','aggregate_grain',None,[],{}]:
            with self.subTest(policy=policy):
                self.p['row_policy']=policy
                with self.assertRaisesRegex(compiler.Error,'row_policy'):
                    compiler.compile_analysis(self.a,self.w,self.p)

    def test_optional_supplier_relationships_preserve_rows(self):
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        db=database(); self.addCleanup(db.close)
        rows=db.execute(sql).fetchall()
        self.assertTrue(any(r[0] is None and r[1] is None and r[3]=='NO_VENDOR' for r in rows))
        self.assertTrue(any(r[0] is None and r[1]=='NO_PARTY' for r in rows))

    def test_composite_key_avoids_line_cross_product(self):
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        db=database(); self.addCleanup(db.close)
        rows=db.execute(sql).fetchall()
        self.assertFalse(any(r[4]==2 and r[5]==2 for r in rows))
        wrong=sql.replace('AND aid.INVOICE_LINE_NUMBER = ail.LINE_NUMBER','')
        self.assertNotEqual(set(db.execute(wrong).fetchall()),set(rows))

    def test_reordering_changes_projection_and_schema_together(self):
        order=[3,5,1,0,2,4]
        a,w=inputs(order=order)
        sql,out=compiler.compile_analysis(a,w,self.p)
        db=database(); self.addCleanup(db.close)
        self.assertEqual([d[0] for d in db.execute(sql).description],[FIELDS[i][5] for i in order])
        self.assertEqual([o['name'] for o in out],[FIELDS[i][5] for i in order])

    def test_literal_filter_is_applied_to_executable_sql(self):
        predicate=existing.expr('sawx:comparison',op='equal',children=existing.expr('sawx:sqlExpression','"Supplier"."Supplier Number"')+existing.expr('xsd:string','0012'))
        a,w=inputs(predicate=predicate)
        sql,_=compiler.compile_analysis(a,w,self.p)
        db=database(); self.addCleanup(db.close)
        self.assertEqual(len(db.execute(sql).fetchall()),4)
        self.assertIn("ps.SEGMENT1 = '0012'",sql)

    def test_wrong_mapping_branch_rejected(self):
        self.p['field_mappings'][0]['database_column']='WRONG'
        with self.assertRaises(compiler.Error): compiler.compile_analysis(self.a,self.w,self.p)

    def test_missing_source_evidence_rejected(self):
        self.p['joins'][1]['evidence']=[]
        with self.assertRaises(compiler.Error): compiler.compile_analysis(self.a,self.w,self.p)

    def test_disconnected_join_rejected(self):
        self.p['joins'][1]['keys']=[['aid.INVOICE_ID','not_joined.INVOICE_ID']]
        with self.assertRaises(compiler.Error): compiler.compile_analysis(self.a,self.w,self.p)

    def test_output_is_not_copied_from_template_sql(self):
        sql,out=compiler.compile_analysis(self.a,self.w,self.p)
        xml,archive=compiler.package_model(template(),sql,out,'ApplicationDB_FSCM','Converted')
        _,_,_,root=compiler.read_model_template(archive)
        ns={'m':compiler.MODEL_NS}
        self.assertEqual(root.find('.//m:sql',ns).text,sql.rstrip())
        self.assertNotIn('OLD_COLUMN',xml.decode())
        self.assertEqual(root.get('defaultDataSourceRef'),'ApplicationDB_FSCM')
        self.assertEqual(root.find('m:validations/m:validation',ns).text,'N')
        els=root.findall('.//m:element',ns)
        self.assertEqual([e.get('name') for e in els],[f[5] for f in FIELDS])
        self.assertEqual([e.get('fieldOrder') for e in els],[str(i) for i in range(1,7)])
        self.assertIn('Converted.xdm',zlib.decompress(archive).decode('utf-8',errors='ignore'))

    def test_model_length_counts_utf8_bytes(self):
        sql,out=compiler.compile_analysis(self.a,self.w,self.p)
        out[0]['heading']='Synthetic caf\u00e9'
        xml,archive=compiler.package_model(template(),sql,out,'ApplicationDB_FSCM','Converted')
        raw,start,end,_=compiler.read_model_template(archive)
        self.assertEqual(end-start,len(xml))
        self.assertEqual(struct.unpack_from('<Q',raw,start-8)[0],len(xml))

    def test_wrong_catalog_length_rejected(self):
        data=bytearray(zlib.decompress(template())); start=data.index(b'<?xml')
        struct.pack_into('<Q',data,start-8,7)
        with self.assertRaises(compiler.Error): compiler.read_model_template(zlib.compress(data))

    def test_no_grain_anchor_no_conversion(self):
        a,w=inputs(order=[0,1,2,3,4])
        with self.assertRaises(compiler.Error): compiler.compile_analysis(a,w,self.p)

    def test_measure_is_not_mislabeled_as_attribute_conversion(self):
        self.a['columns'][0]['expression']='SUM("Supplier"."Supplier Number")'
        with self.assertRaises(compiler.Error): compiler.compile_analysis(self.a,self.w,self.p)

    def test_plan_bound_to_input_hashes_and_outputs_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path=Path(tmp); catalog=path/'source.catalog'; wb=path/'mapping.xlsx'; review=path/'plan.json'
            catalog.write_bytes(zlib.compress(self.a['raw_report_xml'].encode()))
            # Use a deterministic minimal workbook payload from existing helper to test hash rejection first.
            existing.workbook(wb)
            review.write_text(json.dumps(self.p))
            args=argparse.Namespace(catalog=catalog,mapping_workbook=wb,review_plan=review,output_dir=path/'out',template_model=None,analysis_index=None,base_name=None)
            with self.assertRaisesRegex(compiler.Error,'sha256'): compiler.run(args)
            self.assertFalse((path/'out').exists())

    def test_full_cli_produces_candidate_sql_and_catalog(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp); catalog=root/'source with spaces.catalog'; wb=root/'mapping.xlsx'; model=root/'template.xdm.catalog'; review=root/'review.json'; out=root/'out'
            catalog.write_bytes(zlib.compress(self.a['raw_report_xml'].encode()))
            write_workbook(wb,self.w['mappings']);model.write_bytes(template())
            self.p.update(source_catalog_sha256=source.sha256_file(catalog),mapping_workbook_sha256=source.sha256_file(wb),template_model_sha256=source.sha256_file(model))
            review.write_text(json.dumps(self.p))
            before={p:p.read_bytes() for p in (catalog,wb,model,review)}
            cmd=[sys.executable,'-B',str(FOLDER/'compile_reviewed_conversion.py'),str(catalog),'--mapping-workbook',str(wb),'--review-plan',str(review),'--template-model',str(model),'--output-dir',str(out),'--base-name','Converted']
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            summary=json.loads(r.stdout)
            self.assertEqual(summary['conversion_status'],'CANDIDATE_NOT_EXECUTED')
            self.assertEqual(summary['row_policy'],'physical_rows')
            self.assertEqual(json.loads((out/'Converted-manifest.json').read_text())['row_policy'],'physical_rows')
            self.assertEqual(summary['validation']['oracle_execution'],'not_run')
            self.assertEqual(summary['validation']['catalog_round_trip'],'passed')
            self.assertTrue((out/'Converted.xdm.catalog').exists())
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            db=database();self.addCleanup(db.close)
            self.assertEqual(len(db.execute((out/'Converted.sql').read_text()).fetchall()),6)
            generated={p:p.read_bytes() for p in out.iterdir()}
            again=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(again.returncode,1)
            self.assertIn('already exists',again.stderr)
            self.assertEqual(generated,{p:p.read_bytes() for p in generated})

    def test_sort_uses_selected_alias_with_distinct(self):
        self.p['row_policy']='otbi_distinct'
        self.a['sorts']=[dict(expression=self.a['columns'][2]['expression'],direction='descending')]
        sql,_=compiler.compile_analysis(self.a,self.w,self.p)
        self.assertIn('ORDER BY\n    INVOICE_DATE DESC',sql)
        db=database();self.addCleanup(db.close)
        rows=db.execute(sql).fetchall()
        self.assertEqual(rows[0][2],'2026-01-03')

    def test_physical_rows_can_sort_by_unprojected_mapped_attribute(self):
        a,w=inputs(order=[0,1,3,4,5])
        a['sorts']=[dict(expression=self.a['columns'][2]['expression'],direction='descending')]
        sql,_=compiler.compile_analysis(a,w,self.p)
        db=database(); self.addCleanup(db.close)
        rows=db.execute(sql).fetchall()
        self.assertEqual(Counter(rows),Counter(tuple(r[i] for i in [0,1,3,4,5]) for r in db.execute(REFERENCE)))
        self.assertEqual(rows[0][2],'NO_PARTY')
        self.p['row_policy']='otbi_distinct'
        with self.assertRaisesRegex(compiler.Error,'unprojected'):
            compiler.compile_analysis(a,w,self.p)

    def test_changed_source_hash_prevents_stale_plan_use(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp);catalog=root/'source.catalog';wb=root/'mapping.xlsx';review=root/'plan.json'
            catalog.write_bytes(zlib.compress(self.a['raw_report_xml'].encode()));write_workbook(wb,self.w['mappings'])
            self.p.update(source_catalog_sha256=source.sha256_file(catalog),mapping_workbook_sha256=source.sha256_file(wb))
            catalog.write_bytes(zlib.compress(self.a['raw_report_xml'].replace('Supplier Name','Changed Name').encode()))
            review.write_text(json.dumps(self.p))
            args=argparse.Namespace(catalog=catalog,mapping_workbook=wb,review_plan=review,output_dir=root/'out',template_model=None,analysis_index=None,base_name=None)
            with self.assertRaisesRegex(compiler.Error,'source_catalog_sha256'):compiler.run(args)
            self.assertFalse((root/'out').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
