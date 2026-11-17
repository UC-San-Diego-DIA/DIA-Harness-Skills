"""Extract one simple OTBI analysis and its candidate OFC mappings; stdlib only."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

SAW = 'com.siebel.analytics.web/report/v1.1'
EXPR = 'com.siebel.analytics.web/expression/v1.1'
XSI = '{http://www.w3.org/2001/XMLSchema-instance}type'
NS = {'saw': SAW, 'sawx': EXPR}
SS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REF = re.compile(r'"((?:[^"]|"")+)"\s*\.\s*"((?:[^"]|"")+)"(?:\s*\.\s*"((?:[^"]|"")+)")?')


def report_xml(path):
    data = path.read_bytes()
    if not data.lstrip().startswith(b'<'):
        decoder = zlib.decompressobj()
        data = decoder.decompress(data, 50_000_001)
        if len(data) > 50_000_000 or not decoder.eof:
            raise ValueError('Catalog exceeds 50 MB extraction limit or is incomplete')
    reports = []
    for match in re.finditer(rb'<([A-Za-z_][\w.-]*:)?report\b', data):
        end_tag = b'</' + (match.group(1) or b'') + b'report>'
        end = data.find(end_tag, match.end())
        if end < 0:
            raise ValueError('Incomplete report XML')
        xml = data[match.start():end + len(end_tag)]
        root = ET.fromstring(xml)
        if root.tag == '{' + SAW + '}report':
            reports.append((xml, root))
    if len(reports) != 1:
        raise ValueError(f'Expected exactly one complete OTBI report, found {len(reports)}')
    return reports[0]


def mapping_rows(path):
    result = []
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in si.findall('.//s:t', SS))
                       for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', SS)]
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', SS):
            target = rels[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            header = None
            for row in ET.fromstring(archive.read(target)).findall('s:sheetData/s:row', SS):
                cells = {}
                for cell in row.findall('s:c', SS):
                    value = cell.find('s:v', SS)
                    if cell.get('t') == 's' and value is not None:
                        text = strings[int(value.text)]
                    elif cell.get('t') == 'inlineStr':
                        text = ''.join(t.text or '' for t in cell.findall('.//s:t', SS))
                    else:
                        text = value.text if value is not None else ''
                    cells[re.sub(r'\d', '', cell.get('r'))] = text
                if header is None:
                    if 'SUBJECT_AREA' in cells.values():
                        header = cells
                    continue
                item = {name: cells.get(col, '') for col, name in header.items() if name}
                item.update(sheet=sheet.get('name'), row=int(row.get('r')))
                result.append(item)
    if not result:
        raise ValueError('No mapping worksheet with SUBJECT_AREA header')
    return result


def filter_sql(node):
    kind = node.get(XSI, '').split(':')[-1]
    children = list(node)
    op = node.get('op')
    if kind == 'sqlExpression':
        return node.text or ''
    if kind == 'string':
        return "'" + (node.text or '').replace("'", "''") + "'"
    if kind in ('integer', 'decimal', 'double'):
        value = node.text or ''
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value):
            raise ValueError('Invalid numeric literal')
        return value
    if kind == 'logical' and op in ('and', 'or') and children:
        return '(' + ('\n    ' + op.upper() + ' ').join(filter_sql(c) for c in children) + ')'
    if kind == 'list' and op in ('in', 'notIn') and len(children) > 1:
        return filter_sql(children[0]) + (' IN (' if op == 'in' else ' NOT IN (') + ', '.join(filter_sql(c) for c in children[1:]) + ')'
    comparisons = {'equal': '=', 'notEqual': '<>', 'less': '<', 'greater': '>', 'lessOrEqual': '<=', 'greaterOrEqual': '>='}
    if kind == 'comparison' and op in comparisons and len(children) == 2:
        return f'{filter_sql(children[0])} {comparisons[op]} {filter_sql(children[1])}'
    raise ValueError(f'Unsupported filter node: {kind}/{op}; inspect XML rather than dropping it')


def norm(value):
    return value.strip().strip('"')


def extract(catalog, mapping, out):
    xml, root = report_xml(catalog)
    criteria = root.find('saw:criteria', NS)
    if criteria is None or criteria.get(XSI, '').split(':')[-1] != 'simpleCriteria':
        raise ValueError('Only a single simpleCriteria analysis is supported')
    # These change query semantics and need dedicated translation.
    for child in criteria:
        if child.tag not in ('{' + SAW + '}columns', '{' + SAW + '}filter'):
            raise ValueError(f'Unsupported criteria feature: {child.tag}')
    area = norm(criteria.get('subjectArea', ''))
    if not area:
        raise ValueError('Missing subject area')
    columns, used_aliases = [], set()
    for index, column in enumerate(criteria.findall('saw:columns/saw:column', NS), 1):
        if column.get(XSI, '').split(':')[-1] != 'regularColumn':
            raise ValueError('Only regularColumn is supported')
        if set(column.attrib) - {XSI, 'columnID'}:
            raise ValueError('Column attributes require manual semantic review')
        for child in column:
            if child.tag not in {'{' + SAW + '}' + name for name in ['columnFormula', 'displayFormat', 'columnHeading', 'tableHeading']}:
                raise ValueError(f'Unsupported column feature: {child.tag}')
        formula_node = column.find('saw:columnFormula', NS)
        if formula_node is None:
            raise ValueError('Missing column formula')
        if formula_node.attrib:
            raise ValueError('Column aggregation attributes require manual semantic review')
        expr = column.find('saw:columnFormula/sawx:expr', NS)
        if expr is None or expr.get(XSI, '').split(':')[-1] != 'sqlExpression':
            raise ValueError('Missing SQL column formula')
        heading = column.find('saw:columnHeading/saw:caption/saw:text', NS)
        formula = expr.text or ''
        heading = heading.text if heading is not None else None
        if not heading:
            matches = list(REF.finditer(formula))
            heading = (matches[0].group(3) or matches[0].group(2)) if len(matches) == 1 else f'COLUMN_{index}'
        alias = re.sub(r'[^A-Z0-9_]+', '_', heading.strip().upper()).strip('_')[:30] or f'COLUMN_{index}'
        if alias[0].isdigit():
            alias = 'C_' + alias[:28]
        if alias in used_aliases:
            raise ValueError('Duplicate output alias; supply a deliberate naming rule')
        used_aliases.add(alias)
        columns.append(dict(id=column.get('columnID'), heading=heading, alias=alias, formula=formula))
    if not columns:
        raise ValueError('No selected columns')
    filter_node = criteria.find('saw:filter', NS)
    if filter_node is not None and len(filter_node) != 1:
        raise ValueError('Expected one root filter expression')
    where = filter_sql(filter_node[0]) if filter_node is not None else ''
    mappings = mapping_rows(mapping)
    references = {}
    for text in [c['formula'] for c in columns] + [where]:
        for match in REF.finditer(text):
            first, second, third = match.groups()
            ref = (first, second, third) if third else (area, first, second)
            references[ref] = True
    evidence = []
    for ref in references:
        candidates = [r for r in mappings if tuple(norm(r.get(k, '')) for k in ['SUBJECT_AREA', 'PRESENTATION_TABLE', 'PRESENTATION_COLUMN']) == ref]
        sources = sorted({(r.get('DATABASE_OBJECT', ''), r.get('DATABASE_COLUMN', '')) for r in candidates})
        evidence.append(dict(subject_area=ref[0], folder=ref[1], column=ref[2], candidate_database_sources=sources, mapping_rows=candidates, status='unmapped' if not candidates else 'multiple candidates' if len(sources) > 1 else 'candidate only; joins and expression unresolved'))
    ids = {c['id'] for c in columns}
    orphan_ids = sorted({n.get('columnID') for n in root.findall('.//saw:edgeLayer', NS) if n.get('columnID') and n.get('columnID') not in ids})
    inventory = dict(catalog=catalog.name, catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(), mapping=mapping.name,
                     mapping_sha256=hashlib.sha256(mapping.read_bytes()).hexdigest(), subject_area=area, columns=columns, where_sql=where,
                     orphan_layout_column_ids=orphan_ids, grand_total_elements=len(root.findall('.//saw:displayGrandTotal', NS)),
                     tenant_execution='not performed', scope='Logical formulas and filters only. Review original XML for layout and session-dependent behavior.')
    header = '-- BI Publisher SQL dataset. Data source: Oracle BI EE / Oracle BI Server.\n-- Logical SQL, not Fusion database SQL. Extracted formulas and filters.\n-- Tenant execution and reconciliation have not been performed.\n-- Source: ' + catalog.name + '\n-- Grand totals and display formats belong in the BIP layout.\n\n'
    sql = header + 'SELECT\n    ' + ',\n    '.join(c['formula'] + ' AS ' + c['alias'] for c in columns) + '\nFROM "' + area.replace('"', '""') + '"\n'
    if where:
        sql += 'WHERE ' + where + '\n'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'analysis.xml').write_bytes(xml)
    (out / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    (out / 'mapping_evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    (out / 'bip_oracle_bi_ee.sql').write_text(sql, encoding='utf-8')
    return inventory, evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('mapping', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        inventory, evidence = extract(args.catalog, args.mapping, args.out)
    except (ValueError, KeyError, ET.ParseError, zlib.error, zipfile.BadZipFile) as exc:
        parser.exit(2, f'Extraction stopped: {exc}\n')
    print(json.dumps(dict(columns=len(inventory['columns']), references=len(evidence),
                          unmapped=sum(e['status'] == 'unmapped' for e in evidence), output=str(args.out))))
