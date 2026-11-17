#!/usr/bin/env python3
"""Compile reviewed OTBI attributes or additive formulas to Oracle SQL and a BIP model.

The review plan supplies metadata decisions, never a replacement SQL statement.
SQL projections, literal predicates and sort expressions are generated from the catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

import convert_otbi_catalog as source
import aggregate_expressions as aggregate

Error = source.ConversionError
MODEL_NS = 'http://xmlns.oracle.com/oxp/xmlp'
XSD_NS = 'http://www.w3.org/2001/XMLSchema'
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,29}')


def identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise Error(f'Invalid SQL or XML identifier: {value!r}')
    return value


def row_policy(plan: dict) -> str:
    """Keep physical attribute rows unless OTBI distinct output is requested."""
    aggregate_query = plan.get('schema_version') == 2
    default = 'aggregate_grain' if aggregate_query else 'physical_rows'
    policy = plan.get('row_policy', default)
    allowed = {'aggregate_grain'} if aggregate_query else {'physical_rows', 'otbi_distinct'}
    if not isinstance(policy, str) or policy not in allowed:
        raise Error('Invalid row_policy for this compiler schema: ' + str(policy))
    return policy


def require_evidence(record: dict, sources: dict) -> None:
    ids = record.get('evidence', [])
    if not ids or any(key not in sources for key in ids):
        raise Error('Each mapping and join needs a recorded evidence source')


def physical_predicate(record: dict, tables: dict, evidence: dict) -> str:
    """Compile separately evidenced physical scope, never an unchecked SQL string."""
    require_evidence(record, evidence)
    alias = identifier(record['table_alias'])
    column = identifier(record['database_column']).upper()
    if alias not in tables:
        raise Error('Physical restriction references an unjoined object')
    op = record.get('operator')
    if op not in {'=', '<>', '<', '<=', '>', '>=', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL'}:
        raise Error('Unsupported physical restriction operator')
    values = record.get('values', [])
    left = alias + '.' + column
    if op in {'IS NULL', 'IS NOT NULL'}:
        if values:
            raise Error('Null restriction cannot have values')
        return left + ' ' + op
    dtype = record.get('data_type')
    if dtype not in {'string', 'integer', 'decimal', 'date'} or not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
        raise Error('Physical restrictions need typed literal values')
    if op not in {'IN', 'NOT IN'} and len(values) != 1:
        raise Error('Comparison restriction requires one value')
    rendered = []
    for value in values:
        node = ET.Element(f'{{{source.SAWX_NS}}}expr', {f'{{{source.XSI_NS}}}type': 'xsd:' + dtype})
        node.text = value
        rendered.append(source.render_value(node))
    return left + ' ' + op + ' ' + ('(' + ', '.join(rendered) + ')' if op in {'IN', 'NOT IN'} else rendered[0])


def reviewed_bindings(analysis: dict, workbook: dict, plan: dict):
    version = plan.get('schema_version')
    if version not in {1, 2} or plan.get('subject_area') != analysis['subject_area']:
        raise Error('Review plan schema or subject area does not match the analysis')
    for field in ('grain', 'comparison_scope', 'reviewed_by', 'reviewed_at'):
        if not plan.get(field):
            raise Error(f'Review plan requires {field}')
    evidence = plan.get('sources', {})
    if not evidence or any(not x.get('title') or not x.get('location') for x in evidence.values()):
        raise Error('Evidence sources need titles and locations')
    root = ET.fromstring(analysis['raw_report_xml'])
    criteria = root.find('saw:criteria', source.NS)
    if source.expression_type(criteria) not in {'', 'simpleCriteria'} or any(source.local_name(child.tag) not in {'columns', 'filter', 'columnOrder'} for child in criteria):
        raise Error('Reviewed compiler currently supports simple criteria only')
    if any(source.local_name(node.tag) in {'selectionSteps', 'selectionStep', 'steps', 'prompts'} and len(node) for node in root.iter()):
        raise Error('Selection steps and prompt definitions require additional compilation support')

    start = plan['root_table']
    if version == 2:
        require_evidence(start, evidence)
    tables = {identifier(start['alias']): identifier(start['object']).upper()}
    from_lines = [f"FROM {tables[start['alias']]} {start['alias']}"]
    for join in plan.get('joins', []):
        require_evidence(join, evidence)
        if version == 2 and join.get('cardinality') not in {'one-to-one', 'many-to-one'}:
            raise Error('Additive compilation cannot join a multiplying fact branch; aggregate it separately')
        alias, table = identifier(join['alias']), identifier(join['object']).upper()
        if alias in tables or join.get('kind') not in {'INNER', 'LEFT'} or not join.get('cardinality'):
            raise Error('Join requires a new alias, INNER/LEFT kind, and reviewed cardinality')
        predicates = []
        for left, right in join.get('keys', []):
            terms = []
            aliases = []
            for term in (left, right):
                if not isinstance(term, str) or term.count('.') != 1:
                    raise Error('Join key must be an alias.column reference')
                a, col = term.split('.')
                identifier(a); identifier(col)
                aliases.append(a)
                terms.append(f'{a}.{col.upper()}')
            if aliases.count(alias) != 1 or next(a for a in aliases if a != alias) not in tables:
                raise Error('Every join key must connect the new alias to an existing alias')
            predicates.append(' = '.join(terms))
        if not predicates:
            raise Error('Join has no key predicates')
        tables[alias] = table
        if version == 2:
            predicates += [physical_predicate(r, tables, evidence) for r in join.get('restrictions', [])]
        from_lines += [f"{join['kind']} JOIN {table} {alias}", '    ON ' + '\n   AND '.join(predicates)]

    fields = {}
    for binding in plan.get('field_mappings', []):
        require_evidence(binding, evidence)
        ref = binding['presentation_ref']
        if ref in fields or not source.PRESENTATION_REF.fullmatch(ref):
            raise Error('Field bindings require unique complete presentation references')
        alias = identifier(binding['table_alias'])
        col = identifier(binding['database_column']).upper()
        roles = {'attribute', 'measure'} if version == 2 else {'attribute'}
        if alias not in tables or binding.get('semantic_role') not in roles:
            raise Error('Only reviewed attribute fields on joined objects are supported')
        _, candidates = source.mapping_for_expression(ref, analysis['subject_area'], workbook['mappings'])
        exact = [r for r in candidates if r.get('DATABASE_OBJECT', '').upper() == tables[alias] and r.get('DATABASE_COLUMN', '').upper() == col]
        if not exact:
            raise Error(f'Reviewed binding is absent from the Oracle lineage workbook: {ref}')
        fields[ref] = {**binding, 'database_object': tables[alias], 'database_column': col, 'workbook_rows': [r['workbook_row'] for r in exact]}
        if version == 2:
            field = fields[ref]
            field['physical_expression'] = f'{alias}.{col}'
            if field['data_type'] not in {'string', 'integer', 'decimal'}:
                raise Error('Additive expression bindings currently support string and numeric datatypes')
            if field['semantic_role'] == 'measure':
                if field.get('aggregation') != 'SUM' or field['data_type'] not in {'decimal', 'integer'} or alias != start['alias']:
                    raise Error('Additive measures require SUM on the reviewed root fact')
                if any(not field.get(k) for k in ('input_grain', 'currency', 'row_selection')):
                    raise Error('Measure needs reviewed input grain, currency and row-selection semantics')
            if field.get('descriptor'):
                descriptor = field['descriptor'] = dict(field['descriptor'])
                require_evidence(descriptor, evidence)
                da = identifier(descriptor['table_alias'])
                dc = identifier(descriptor['database_column']).upper()
                if da not in tables or not descriptor.get('lineage'):
                    raise Error('Descriptor key requires joined-object lineage separate from display-number mapping')
                descriptor['physical_expression'] = f'{da}.{dc}'
    return root, tables, from_lines, fields


def compile_analysis(analysis: dict, workbook: dict, plan: dict) -> tuple[str, list[dict]]:
    policy = row_policy(plan)
    if plan.get('schema_version') == 2:
        return compile_aggregate_analysis(analysis, workbook, plan)
    root, tables, from_lines, fields = reviewed_bindings(analysis, workbook, plan)

    def resolve_binding(match):
        ref = match.group(0)
        binding = fields.get(ref)
        if binding is None:
            signature = tuple(match.group(k) for k in ('subject', 'table', 'column'))
            binding = next((b for r, b in fields.items() if tuple(source.PRESENTATION_REF.fullmatch(r).group(k) for k in ('subject', 'table', 'column')) == signature), None)
        if binding is None:
            raise Error(f'No reviewed mapping for {ref}')
        return binding

    def translate(expression: str) -> str:
        source.validate_physical_expression(expression)
        parts = source.sql_parts(expression)

        def replace(match):
            binding = resolve_binding(match)
            return f"{binding['table_alias']}.{binding['database_column']}"

        for i in range(0, len(parts), 2):
            parts[i] = source.PRESENTATION_REF.sub(replace, parts[i])
        return ''.join(parts)

    outputs, projections, names = [], [], set()
    for position, column in enumerate(analysis['columns'], 1):
        expr = column['expression']
        if not source.PRESENTATION_REF.fullmatch(expr):
            raise Error('Reviewed v1 compiles direct attributes only; measures and scalar outputs need a supported semantic compiler')
        translated = translate(expr)
        binding = resolve_binding(source.PRESENTATION_REF.fullmatch(expr))
        name = identifier(binding['output_name']).upper()
        if name in names:
            raise Error('Duplicate output names; record distinct reviewed output bindings')
        names.add(name)
        datatype = binding['data_type']
        if datatype not in {'string', 'date', 'decimal', 'integer', 'dateTime'}:
            raise Error('Unsupported output datatype')
        outputs.append(dict(name=name, heading=column['heading'], data_type=datatype, position=position, expression=expr, physical_expression=translated))
        projections.append(f'    {translated} AS {name}')

    # Distinct projected tuples and physical fact rows are different contracts.
    lines = ['-- Generated from the selected OTBI analysis and reviewed field/join evidence.',
             '-- Candidate SQL; Oracle execution and OTBI result comparison are recorded separately.',
             '-- Row policy: ' + policy + '.',
             'SELECT DISTINCT' if policy == 'otbi_distinct' else 'SELECT',
             ',\n'.join(projections), *from_lines]
    if analysis['filter']['explicit_sql']:
        lines += ['WHERE', '    ' + translate(analysis['filter']['explicit_sql'])]
    if analysis['sorts']:
        ordered = []
        expressions = {o['physical_expression']: o['name'] for o in outputs}
        for sort in analysis['sorts']:
            physical = translate(sort['expression'])
            if physical not in expressions and policy == 'otbi_distinct':
                raise Error('DISTINCT output cannot sort on an unprojected field')
            ordered.append(expressions.get(physical, physical) + ' ' + source.sort_direction(sort['direction']))
        lines += ['ORDER BY', '    ' + ', '.join(ordered)]
    anchors = plan.get('required_projected_refs', [])
    selected_refs = {o['expression'] for o in outputs}
    if not anchors or not all(ref in selected_refs for ref in anchors):
        raise Error('The reviewed grain anchors are missing from the projection')
    return '\n'.join(lines) + '\n', outputs


def compile_aggregate_analysis(analysis: dict, workbook: dict, plan: dict) -> tuple[str, list[dict]]:
    root, tables, from_lines, fields = reviewed_bindings(analysis, workbook, plan)
    evidence = plan['sources']
    scope = plan.get('physical_scope', {})
    require_evidence(scope, evidence)
    if scope.get('status') != 'reviewed' or not isinstance(scope.get('restrictions'), list):
        raise Error('Physical row scope and hidden predicates require an explicit reviewed restriction list')
    fact = plan.get('fact_grain', {})
    require_evidence(fact, evidence)
    if not fact.get('keys'):
        raise Error('Additive compilation requires the root fact key')
    for key in fact['keys']:
        terms = key.split('.')
        if len(terms) != 2 or terms[0] != plan['root_table']['alias']:
            raise Error('Fact key must belong to the root alias')
        identifier(terms[1])
    translator = aggregate.Translator(analysis['subject_area'], list(fields.values()))
    where, resolutions = aggregate.resolve_runtime_filter(analysis, plan.get('runtime_values', {}), evidence)
    predicate = translator.compile(where) if where else None
    if predicate and (predicate.level == 'aggregate' or predicate.kind != 'boolean'):
        raise Error('Criteria filters require row-level predicates')
    bindings = plan.get('output_bindings', [])
    columns = analysis['columns']
    if len(bindings) != len(columns) or {x['column_id'] for x in bindings} != {x['column_id'] for x in columns}:
        raise Error('Output bindings must identify every source column exactly once')
    by_id = {x['column_id']: x for x in bindings}
    outputs, dimensions, names = [], [], set()
    for column in columns:
        record = by_id[column['column_id']]
        name = identifier(record['output_name']).upper()
        if name in names:
            raise Error('Duplicate output names')
        names.add(name)
        result = translator.compile(column['expression'])
        if result.level == 'row' and not source.PRESENTATION_REF.fullmatch(column['expression']):
            raise Error('Grouped dimensions must be direct attribute references')
        if result.kind not in {'numeric', 'text'}:
            raise Error('Unsupported aggregate output datatype')
        heading = column['heading']
        if 'heading' in record and record['heading'] != heading:
            require_evidence(record, evidence)
            heading = record['heading']
        node = next(e for e in root.findall('.//saw:criteria/saw:columns/saw:column', source.NS) if e.get('columnID') == column['column_id'])
        hidden = any(e.get('visibility') == 'hidden' for e in node.iter())
        out = dict(name=name, heading=heading, data_type='decimal' if result.kind == 'numeric' else 'string',
                   column_id=column['column_id'], expression=column['expression'], physical_expression=result.sql,
                   level=result.level, hidden=hidden)
        outputs.append(out)
        if result.level == 'row':
            dimensions.append(out)
    if not any(o['level'] == 'aggregate' for o in outputs):
        raise Error('Use the attribute compiler for a query without additive measures')
    if not dimensions:
        raise Error('This additive scope requires a grouped attribute dimension')
    selected = {o['expression'] for o in dimensions}
    anchors = plan.get('required_projected_refs', [])
    if not anchors or not all(x in selected for x in anchors):
        raise Error('Reviewed result-grain anchors must be selected dimensions')
    views = [e for e in root.iter() if source.expression_type(e) == 'tableView']
    if plan.get('table_view'):
        views = [v for v in views if v.get('name') == plan['table_view']]
    if len(views) != 1:
        raise Error('Select one saved table view for aggregate output')
    view = views[0]
    # Page/section/pivot grouping is a different result contract.
    for edge in view.findall('.//saw:edge', source.NS):
        if edge.get('axis') != 'row' and edge.findall('.//saw:edgeLayer', source.NS):
            raise Error('Only a flat row table view is supported')
    order = [e.get('columnID') for e in view.findall('.//saw:edge[@axis="row"]//saw:edgeLayer', source.NS)]
    if len(order) != len(columns) or set(order) != set(by_id):
        raise Error('Saved table view must account for every source column')
    total_nodes = view.findall('.//saw:displayGrandTotal', source.NS)
    totals = bool(total_nodes)
    if totals and (len(total_nodes) != 1 or total_nodes[0].get('grandTotalPosition') != 'after' or len(dimensions) != 1 or dimensions[0]['data_type'] != 'string'):
        raise Error('Grand totals currently require one text dimension and an after-row total')
    if totals:
        total_review = plan.get('grand_total', {})
        require_evidence(total_review, evidence)
        if total_review.get('method') != 'recompute_source_formulas':
            raise Error('Grand-total aggregate stage needs an explicit reviewed method')
    internals = {o['column_id']: o for o in outputs}
    visible = [internals[cid] for cid in order if not internals[cid]['hidden']]
    group = ', '.join(o['physical_expression'] for o in dimensions)
    projections = []
    for out in outputs:
        expr = out['physical_expression']
        if totals and out['level'] == 'row':
            expr = f"CASE WHEN GROUPING({expr}) = 1 THEN 'Grand Total' ELSE {expr} END"
        projections.append(f'    {expr} AS {out["name"]}')
    total_alias = 'OTBI_TOTAL_ROW'
    if total_alias in names:
        raise Error('Output alias conflicts with the reserved total-row marker')
    projections.append(f'    {"GROUPING(" + group + ")" if totals else "0"} AS {total_alias}')
    lines = ['-- Generated additive candidate. Physical mappings and fact predicates require separate evidence.',
             '-- Oracle execution and complete OTBI comparison remain separate acceptance checks.',
             'WITH OTBI_GROUPED AS (', 'SELECT', ',\n'.join(projections), *from_lines]
    restrictions = [physical_predicate(r, tables, evidence) for r in scope['restrictions']]
    if predicate:
        restrictions.insert(0, predicate.sql)
    if restrictions:
        lines += ['WHERE', '    ' + '\n    AND '.join('(' + r + ')' for r in restrictions)]
    lines += ['GROUP BY ' + (f'GROUPING SETS (({group}), ())' if totals else group), ')',
              'SELECT', ',\n'.join('    ' + o['name'] for o in visible), 'FROM OTBI_GROUPED']
    sorts = []
    if totals:
        sorts.append(total_alias + ' ASC')
    if analysis['sorts'] and plan.get('result_sort'):
        raise Error('Runtime sorting cannot silently replace saved criterion sorts')
    for sort in analysis['sorts']:
        match = next((o for o in outputs if o['expression'] == sort['expression']), None)
        if match is None:
            raise Error('Sort expression must identify a selected column')
        sorts.append(match['name'] + ' ' + source.sort_direction(sort['direction']))
    for sort in plan.get('result_sort', []):
        require_evidence(sort, evidence)
        nulls = sort.get('nulls', '')
        if nulls not in {'FIRST', 'LAST'} or sort['column_id'] not in internals:
            raise Error('Runtime sort needs a selected column and explicit null order')
        sorts.append(internals[sort['column_id']]['name'] + ' ' + source.sort_direction(sort['direction']) + ' NULLS ' + nulls)
    if sorts:
        lines += ['ORDER BY ' + ', '.join(sorts)]
    for position, out in enumerate(visible, 1):
        out['position'] = position
        out['runtime_resolutions'] = resolutions
    return '\n'.join(lines) + '\n', visible


def read_model_template(data: bytes) -> tuple[bytes, int, int, ET.Element]:
    try:
        stream = zlib.decompressobj()
        raw = stream.decompress(data)
    except zlib.error as exc:
        raise Error('Template must use the supported zlib .xdm.catalog format') from exc
    if not stream.eof or stream.unused_data:
        raise Error('Incomplete or concatenated model template archive')
    marker = raw.find(b'<dataModel')
    start = raw.rfind(b'<?xml', 0, marker)
    if start < 0:
        raise Error('Model template lacks a supported XML declaration')
    if start < 10 or raw[start-10:start-8] != b'\x01\x00':
        raise Error('Unsupported catalog model-payload record header')
    size = struct.unpack_from('<Q', raw, start-8)[0]
    end = start + size
    if end > len(raw) or raw[end:] != b'\x02\x00':
        raise Error('Model-payload length or catalog trailer does not match supported format')
    try:
        root = ET.fromstring(raw[start:end])
    except ET.ParseError as exc:
        raise Error('Malformed data model XML') from exc
    if root.tag != f'{{{MODEL_NS}}}dataModel':
        raise Error('Template is not a BI Publisher data model')
    return raw, start, end, root


def package_model(template: bytes, sql: str, outputs: list[dict], data_source: str, name: str) -> tuple[bytes, bytes]:
    raw, start, end, root = read_model_template(template)
    prefix = raw[:start-8]
    # Rename only the root item in its checked, length-prefixed JSON record.
    renamed = False
    for match in re.finditer(rb'\{', prefix):
        i = match.start()
        if i < 4:
            continue
        n = struct.unpack_from('<I', prefix, i-4)[0]
        if n < 2 or i+n > len(prefix):
            continue
        try:
            item = json.loads(prefix[i:i+n])
        except (ValueError, UnicodeDecodeError):
            continue
        if item.get('ItemType') != 1 or not str(item.get('ItemName', '')).endswith('.xdm'):
            continue
        if item.get('ObjectSignature'):
            raise Error('Signed catalog templates are not supported')
        item['ItemName'] = name + '.xdm'
        if 'OriginalPath' in item:
            item['OriginalPath'] = item['OriginalPath'].rsplit('/', 1)[0] + '/' + item['ItemName']
        encoded = json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        prefix = prefix[:i-4] + struct.pack('<I', len(encoded)) + encoded + prefix[i+n:]
        renamed = True
        break
    if not renamed:
        raise Error('No supported root data model item found in template metadata')

    ns = {'m': MODEL_NS}
    datasets = root.findall('./m:dataSets/m:dataSet', ns)
    if len(datasets) != 1 or datasets[0].get('type') != 'complex':
        raise Error('Template must contain exactly one complex SQL dataset')
    for tag in ('parameters', 'lexicals', 'eventTriggers', 'bursting', 'valueSets'):
        node = root.find(f'm:{tag}', ns)
        if node is not None and len(node):
            raise Error(f'Template has {tag}; this packaging version requires an unparameterized model')
    query = datasets[0].find('m:sql', ns)
    groups = root.findall('.//m:group', ns)
    if query is None or len(groups) != 1 or groups[0].get('source') != datasets[0].get('name'):
        raise Error('Template requires one SQL query and one matching output group')
    root.set('defaultDataSourceRef', data_source)
    query.set('dataSourceRef', data_source)
    query.text = sql.rstrip()
    group = groups[0]
    for child in list(group):
        group.remove(child)
    for out in outputs:
        ET.SubElement(group, f'{{{MODEL_NS}}}element', dict(name=out['name'], value=out['name'], label=out['heading'], dataType='xsd:'+out['data_type'], breakOrder='', fieldOrder=str(out['position'])))
    validation = root.find('m:validations/m:validation', ns)
    if validation is not None:
        validation.text = 'N'
    root.set('xmlns:xsd', XSD_NS)
    ET.register_namespace('', MODEL_NS)
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'
    ET.fromstring(xml)
    archive = zlib.compress(prefix + struct.pack('<Q', len(xml)) + xml + raw[end:])
    rebuilt, a, b, parsed = read_model_template(archive)
    if rebuilt[a:b] != xml or parsed.find('.//m:sql', ns).text != sql.rstrip():
        raise Error('Packaged model failed round-trip verification')
    return xml, archive


def run(args) -> dict:
    catalog = args.catalog.resolve()
    workbook_path = args.mapping_workbook.resolve()
    plan = json.loads(args.review_plan.read_text(encoding='utf-8-sig'))
    for field, path in (('source_catalog_sha256', catalog), ('mapping_workbook_sha256', workbook_path)):
        if plan.get(field) != source.sha256_file(path):
            raise Error(f'Review plan {field} does not match its input')
    analyses = source.extract_catalog(catalog, inspect_only=True)
    if args.analysis_index is None and len(analyses) != 1:
        raise Error('Select exactly one analysis using --analysis-index')
    index = args.analysis_index if args.analysis_index is not None else 1
    if not 1 <= index <= len(analyses):
        raise Error('Analysis index is out of range')
    analysis = source.extract_report(analyses[index-1]['raw_report_xml'], index-1, inspect_only=plan.get('schema_version') == 2)
    sql, outputs = compile_analysis(analysis, source.read_mapping_workbook(workbook_path), plan)
    name = source.safe_base_name(args.base_name or catalog.stem + '-Converted')
    directory = args.output_dir.resolve()
    content = {name+'.sql': sql.encode('utf-8')}
    template_info = None
    if args.template_model:
        template_path = args.template_model.resolve()
        template_hash = source.sha256_file(template_path)
        if plan.get('template_model_sha256') != template_hash:
            raise Error('Review plan template_model_sha256 does not match the supplied template')
        xml, archive = package_model(template_path.read_bytes(), sql, outputs, plan['data_source'], name)
        content[name+'.xdm'] = xml
        content[name+'.xdm.catalog'] = archive
        template_info = {'path': str(template_path), 'sha256': template_hash}
    manifest = dict(schema_version=1, conversion_status='CANDIDATE_NOT_EXECUTED', row_policy=row_policy(plan), source_catalog=dict(path=str(catalog), sha256=source.sha256_file(catalog)), mapping_workbook=dict(path=str(workbook_path), sha256=source.sha256_file(workbook_path)), review_plan=plan, template_model=template_info, analysis=analysis, outputs=outputs, sql_sha256=hashlib.sha256(content[name+'.sql']).hexdigest(), validation=dict(sql_generation='passed', catalog_round_trip='passed' if template_info else 'not_requested', oracle_execution='not_run', oracle_catalog_import='not_run', otbi_reconciliation='not_run'))
    content[name+'-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    conflicts = [str(directory / file) for file in content if (directory/file).exists()]
    if conflicts:
        raise Error('Output already exists; choose a new output location:\n'+'\n'.join(conflicts))
    if any((directory/file).resolve() == path for file in content for path in (catalog, workbook_path, args.review_plan.resolve(), args.template_model.resolve() if args.template_model else catalog)):
        raise Error('Output would replace an input')
    directory.mkdir(parents=True, exist_ok=True)
    for file, data in content.items():
        (directory/file).write_bytes(data)
    return dict(conversion_status=manifest['conversion_status'], row_policy=manifest['row_policy'], column_count=len(outputs), outputs=[str(directory/file) for file in content], validation=manifest['validation'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('catalog', type=Path)
    p.add_argument('--mapping-workbook', type=Path, required=True)
    p.add_argument('--review-plan', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--template-model', type=Path)
    p.add_argument('--analysis-index', type=int)
    p.add_argument('--base-name')
    try:
        result = run(p.parse_args())
    except (Error, OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
