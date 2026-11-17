"""Typed translation of reviewed additive OTBI expressions. No physical source guessing."""
from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET

import convert_otbi_catalog as source

Error = source.ConversionError


def reference_key(ref: str, subject: str) -> tuple[str, str, str]:
    m = source.PRESENTATION_REF.fullmatch(ref)
    if m is None:
        raise Error('Expected a complete presentation reference')
    area = m.group('subject')
    return (area[1:-1].replace('""', '"') if area else subject,
            m.group('table').replace('""', '"'), m.group('column').replace('""', '"'))


@dataclass(frozen=True)
class Expression:
    sql: str
    level: str  # constant, row, aggregate
    kind: str   # numeric, text, boolean, null


class Translator:
    """Small grammar for FILTER, IFNULL, descriptor keys, arithmetic and predicates.

    Bindings supply already-reviewed physical references. SUM is the only supported
    measure aggregation. Every predicate stays at row level inside its own FILTER.
    """
    def __init__(self, subject: str, bindings: list[dict]):
        self.subject = subject
        self.bindings = {}
        for binding in bindings:
            key = reference_key(binding['presentation_ref'], subject)
            if key in self.bindings:
                raise Error('Duplicate semantic field binding')
            self.bindings[key] = binding

    def binding(self, ref):
        try:
            return self.bindings[reference_key(ref, self.subject)]
        except KeyError as exc:
            raise Error(f'No reviewed mapping for {ref}') from exc

    def compile(self, text: str) -> Expression:
        return Parser(text, self).parse()


class Parser:
    def __init__(self, text, translator):
        self.translator = translator
        self.tokens = []
        i = 0
        while i < len(text):
            if text[i].isspace():
                i += 1
                continue
            ref = source.PRESENTATION_REF.match(text, i)
            token = re.match(r"'(?:[^']|'')*'|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z_][A-Za-z_0-9]*|<>|!=|<=|>=|[(),+*/=<>-]", text[i:]) if ref is None else None
            if ref:
                self.tokens.append(('ref', ref.group(0)))
                i = ref.end()
            elif token:
                value = token.group(0)
                kind = 'string' if value.startswith("'") else 'number' if value[0].isdigit() or value[0] == '.' else 'word'
                self.tokens.append((kind, value))
                i += len(value)
            else:
                raise Error(f'Unsupported formula token near {text[i:i+40]!r}')
        self.tokens.append(('end', '<end>'))
        self.i = 0

    def peek(self):
        kind, value = self.tokens[self.i]
        return value.upper() if kind == 'word' else value

    def take(self, expected=None):
        token = self.tokens[self.i]
        if expected is not None and self.peek() != expected:
            raise Error(f'Expected {expected}, found {token[1]}')
        self.i += 1
        return token

    def parse(self):
        result = self.expression()
        self.take('<end>')
        return result

    @staticmethod
    def combine(left, right, sql, kind):
        levels = {left.level, right.level} - {'constant'}
        if levels == {'row', 'aggregate'}:
            raise Error('Mixed row and aggregate expression requires an explicit aggregate stage')
        return Expression(sql, next(iter(levels), 'constant'), kind)

    def expression(self, minimum=0):
        left = self.atom()
        precedence = {'OR': 1, 'AND': 2, '=': 3, '<>': 3, '!=': 3, '<': 3, '>': 3, '<=': 3, '>=': 3,
                      'IN': 3, 'NOT': 3, 'LIKE': 3, 'IS': 3, '+': 4, '-': 4, '*': 5, '/': 5}
        while self.peek() in precedence and precedence[self.peek()] >= minimum:
            op = self.take()[1].upper()
            priority = precedence[op]
            if op == 'NOT':
                op += ' ' + self.take()[1].upper()
                if op not in {'NOT IN', 'NOT LIKE'}:
                    raise Error('Unsupported predicate after NOT')
            if op in {'IN', 'NOT IN'}:
                self.take('(')
                values = [self.expression(4)]
                while self.peek() == ',':
                    self.take(','); values.append(self.expression(4))
                self.take(')')
                if left.level == 'aggregate' or any(x.level != 'constant' for x in values):
                    raise Error('IN needs a row value and constant list')
                if any(x.kind not in {left.kind, 'null'} for x in values):
                    raise Error('IN list datatype does not match its field')
                left = Expression(f'({left.sql} {op} ({", ".join(x.sql for x in values)}))', left.level, 'boolean')
                continue
            if op == 'IS':
                negate = self.peek() == 'NOT'
                if negate:
                    self.take('NOT')
                self.take('NULL')
                left = Expression(f'({left.sql} IS {"NOT " if negate else ""}NULL)', left.level, 'boolean')
                continue
            right = self.expression(priority + 1)
            if op in {'AND', 'OR'}:
                if left.kind != 'boolean' or right.kind != 'boolean':
                    raise Error('Logical operators require predicates')
                kind = 'boolean'
            elif op in {'+', '-', '*', '/'}:
                if left.kind != 'numeric' or right.kind != 'numeric':
                    raise Error('Arithmetic requires numeric operands')
                kind = 'numeric'
            else:
                if left.kind != right.kind and 'null' not in {left.kind, right.kind}:
                    raise Error('Comparison operand datatypes differ')
                if op in {'LIKE', 'NOT LIKE'} and left.kind != 'text':
                    raise Error('LIKE requires text')
                kind = 'boolean'
            left = self.combine(left, right, f'({left.sql} {op} {right.sql})', kind)
        return left

    def atom(self):
        kind, value = self.take()
        keyword = value.upper() if kind == 'word' else value
        if kind == 'ref':
            binding = self.translator.binding(value)
            physical = binding['physical_expression']
            if binding['semantic_role'] == 'measure':
                if binding.get('aggregation') != 'SUM':
                    raise Error('Only evidence-backed SUM measures are supported')
                return Expression(f'SUM({physical})', 'aggregate', 'numeric')
            return Expression(physical, 'row', 'numeric' if binding['data_type'] in {'integer', 'decimal'} else 'text')
        if kind in {'number', 'string'} or keyword == 'NULL':
            return Expression(value, 'constant', 'numeric' if kind == 'number' else 'text' if kind == 'string' else 'null')
        if keyword == '(':
            result = self.expression(); self.take(')')
            return Expression('(' + result.sql + ')', result.level, result.kind)
        if keyword in {'+', '-', 'NOT'}:
            result = self.expression(3 if keyword == 'NOT' else 6)
            if result.kind != ('boolean' if keyword == 'NOT' else 'numeric'):
                raise Error('Invalid unary operator operand')
            return Expression(f'({keyword} {result.sql})', result.level, result.kind)
        if keyword == 'FILTER':
            self.take('(')
            ref = self.take()
            if ref[0] != 'ref':
                raise Error('FILTER requires a direct reviewed additive measure')
            binding = self.translator.binding(ref[1])
            if binding.get('semantic_role') != 'measure' or binding.get('aggregation') != 'SUM':
                raise Error('FILTER requires an evidence-backed SUM measure')
            self.take('USING')
            predicate = self.expression(); self.take(')')
            if predicate.kind != 'boolean' or predicate.level == 'aggregate':
                raise Error('FILTER predicate must be a row-level predicate')
            return Expression(f'SUM(CASE WHEN {predicate.sql} THEN {binding["physical_expression"]} END)', 'aggregate', 'numeric')
        if keyword == 'DESCRIPTOR_IDOF':
            self.take('('); ref = self.take(); self.take(')')
            if ref[0] != 'ref':
                raise Error('DESCRIPTOR_IDOF requires a mapped presentation field')
            binding = self.translator.binding(ref[1])
            descriptor = binding.get('descriptor')
            if not descriptor or descriptor.get('data_type') not in {'integer', 'decimal', 'string'}:
                raise Error('Descriptor key needs separate reviewed lineage and datatype')
            return Expression(descriptor['physical_expression'], 'row', 'text' if descriptor['data_type'] == 'string' else 'numeric')
        if keyword in {'IFNULL', 'NVL', 'COALESCE', 'NULLIF'}:
            self.take('('); values = [self.expression()]
            while self.peek() == ',':
                self.take(','); values.append(self.expression())
            self.take(')')
            if len(values) < 2 or (keyword != 'COALESCE' and len(values) != 2):
                raise Error('Null function has incorrect argument count')
            result = values[0]
            for other in values[1:]:
                if other.kind != result.kind and 'null' not in {other.kind, result.kind}:
                    raise Error('Null function operand datatypes differ')
                result = self.combine(result, other, '', other.kind if result.kind == 'null' else result.kind)
            function = 'COALESCE' if keyword == 'IFNULL' else keyword
            return Expression(f'{function}({", ".join(x.sql for x in values)})', result.level, result.kind)
        raise Error(f'Unsupported function or expression: {value}')


def resolve_runtime_filter(analysis: dict, runtime: dict, evidence: dict) -> tuple[str, list[dict]]:
    """Expand typed external prompt selections without changing saved XML/defaults."""
    xml = analysis['filter']['raw_xml']
    if not xml:
        if runtime:
            raise Error('Runtime values supplied for an analysis with no filter variables')
        return '', []
    root = ET.fromstring(xml)
    used, resolutions = set(), []
    for parent in list(root.iter()):
        for child in list(parent):
            if source.expression_type(child) != 'eval':
                continue
            name = source.expression_text(child)
            record = runtime.get(name)
            if not record or not record.get('values') or not record.get('evidence') or any(k not in evidence for k in record['evidence']):
                raise Error(f'Effective values and user evidence required for prompt {name}; a saved default is insufficient')
            values = record['values']
            dtype = record.get('data_type')
            if not isinstance(values, list) or dtype not in {'string', 'integer', 'decimal', 'date'} or any(not isinstance(x, str) for x in values):
                raise Error('Runtime values must be typed lists of literal strings')
            if len(values) > 1 and (source.expression_type(parent) != 'list' or parent.get('op') not in {'in', 'notIn'} or list(parent)[0] is child):
                raise Error('Multiple prompt values require an IN/NOT IN value position')
            index = list(parent).index(child)
            parent.remove(child)
            for offset, value in enumerate(values):
                node = ET.Element(f'{{{source.SAWX_NS}}}expr', {f'{{{source.XSI_NS}}}type': 'xsd:' + dtype})
                node.text = value
                source.render_value(node)  # Validate and escape through the existing typed literal path.
                parent.insert(index + offset, node)
            used.add(name)
            resolutions.append(dict(variable=name, saved_default=child.get('default'), **record))
    if used != set(runtime):
        raise Error('Unused or misspelled runtime variable names')
    return source.render_expression(root) or '', resolutions
